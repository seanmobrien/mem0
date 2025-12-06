from datetime import datetime, UTC
from typing import List, Optional, Set, Union
from uuid import UUID, uuid4
import logging
import os
from functools import wraps
from fastapi import Request
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate
from pydantic import BaseModel
from sqlalchemy import or_, func
from app.utils.memory import get_memory_client
from app.utils.memory_client import search_memories, log_memory_access
from qdrant_client import models as qdrant_models

from app.database import get_db
from app.models import (
    Memory, MemoryState, MemoryAccessLog, App,
    MemoryStatusHistory, User, Category, AccessControl, Config as ConfigModel
)
from app.schemas import MemoryResponse, PaginatedMemoryResponse
from app.utils.permissions import check_memory_access_permissions
from app.auth import get_current_user, get_user_id, get_user_record
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])

_TRACER = trace.get_tracer("mem0.api.memories")


def _record_exception(span, exc: Exception) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def traced_endpoint(span_name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with _TRACER.start_as_current_span(span_name, kind=SpanKind.SERVER) as span:
                try:
                    # Try to enrich span with common attributes from args/kwargs
                    # user (dependency) is commonly passed as 'user'
                    user = kwargs.get("user")
                    if not user:
                        # search positional args for a user-like object (has user_id)
                        for a in args:
                            if hasattr(a, "user_id"):
                                user = a
                                break
                    if user and hasattr(user, "user_id"):
                        span.set_attribute("mem0.user_id", getattr(user, "user_id"))

                    # app_id or app parameter
                    app_id = kwargs.get("app_id") or kwargs.get("app")
                    if not app_id and "request" in kwargs and hasattr(kwargs["request"], "path_params"):
                        # try to derive from path params
                        path_params = getattr(kwargs["request"], "path_params", {})
                        if "app_id" in path_params:
                            app_id = path_params["app_id"]
                    if app_id:
                        span.set_attribute("mem0.app_id", str(app_id))

                    # If Request present, add route details
                    request = kwargs.get("request")
                    if not request:
                        for a in args:
                            if isinstance(a, Request):
                                request = a
                                break
                    if request:
                        try:
                            span.set_attribute("http.method", request.method)
                            span.set_attribute("http.target", str(getattr(request, "url", "")))
                        except Exception:
                            pass

                    return await func(*args, **kwargs)
                except Exception as exc:
                    _record_exception(span, exc)
                    raise

        return wrapper

    return decorator


def get_memory_or_404(db: Session, memory_id: UUID, user: User) -> Memory:
    memory = db.query(Memory).filter(Memory.id == memory_id).first()
    if not memory or memory.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


def update_memory_state(db: Session, memory_id: UUID, new_state: MemoryState, user: User):
    memory = get_memory_or_404(db, memory_id, user)
    old_state = memory.state

    # Update memory state
    memory.state = new_state
    if new_state == MemoryState.archived:
        memory.archived_at = datetime.now(UTC)
    elif new_state == MemoryState.deleted:
        memory.deleted_at = datetime.now(UTC)

    # Record state change
    history = MemoryStatusHistory(
        memory_id=memory_id,
        changed_by=user.id,
        old_state=old_state,
        new_state=new_state
    )
    db.add(history)
    db.commit()
    return memory


def get_accessible_memory_ids(db: Session, app_id: UUID, user: User) -> Set[UUID]:
    """
    Get the set of memory IDs that the app has access to based on app-level ACL rules.
    Returns all memory IDs if no specific restrictions are found.
    """
    # Get app-level access controls
    app_access = db.query(AccessControl).filter(
        AccessControl.subject_type == "app",
        AccessControl.subject_id == app_id,
        AccessControl.object_type == "memory"
    ).all()

    # If no app-level rules exist, return None to indicate all memories are accessible
    if not app_access :
        return None

    # Initialize sets for allowed and denied memory IDs
    allowed_memory_ids = set()
    denied_memory_ids = set()

    # Process app-level rules
    for rule in app_access:
        if rule.effect == "allow":
            if rule.object_id:  # Specific memory access
                allowed_memory_ids.add(rule.object_id)
            else:  # All memories access
                return None  # All memories allowed
        elif rule.effect == "deny":
            if rule.object_id:  # Specific memory denied
                denied_memory_ids.add(rule.object_id)
            else:  # All memories denied
                return set()  # No memories accessible

    # Remove denied memories from allowed set
    if allowed_memory_ids:
        allowed_memory_ids -= denied_memory_ids

    return allowed_memory_ids


# List all memories with filtering
@router.get("/", response_model=Page[MemoryResponse])
@traced_endpoint("memories.list")
async def list_memories(
    app_id: Optional[UUID] = None,
    from_date: Optional[int] = Query(
        None,
        description="Filter memories created after this date (timestamp)",
        examples=[1718505600]
    ),
    to_date: Optional[int] = Query(
        None,
        description="Filter memories created before this date (timestamp)",
        examples=[1718505600]
    ),
    categories: Optional[str] = None,
    params: Params = Depends(),
    search_query: Optional[str] = None,
    sort_column: Optional[str] = Query(None, description="Column to sort by (memory, categories, app_name, created_at)"),
    sort_direction: Optional[str] = Query(None, description="Sort direction (asc or desc)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    if app_id:
        span.set_attribute("mem0.app_id", str(app_id))
    if search_query:
        span.set_attribute("mem0.search_query", search_query)
    # Build base query
    query = db.query(Memory).filter(
        Memory.user_id == user.id,
        Memory.state != MemoryState.deleted,
        Memory.state != MemoryState.archived,
        Memory.content.ilike(f"%{search_query}%") if search_query else True
    )

    # Apply filters
    if app_id:
        query = query.filter(Memory.app_id == app_id)

    if from_date:
        from_datetime = datetime.fromtimestamp(from_date, tz=UTC)
        query = query.filter(Memory.created_at >= from_datetime)

    if to_date:
        to_datetime = datetime.fromtimestamp(to_date, tz=UTC)
        query = query.filter(Memory.created_at <= to_datetime)

    # Add joins for app and categories after filtering
    query = query.outerjoin(App, Memory.app_id == App.id)
    query = query.outerjoin(Memory.categories)

    # Apply category filter if provided
    if categories:
        category_list = [c.strip() for c in categories.split(",")]
        query = query.filter(Category.name.in_(category_list))

    # Apply sorting if specified
    if sort_column:
        sort_field = getattr(Memory, sort_column, None)
        if sort_field:
            query = query.order_by(sort_field.desc()) if sort_direction == "desc" else query.order_by(sort_field.asc())


    # Get paginated results
    paginated_results = sqlalchemy_paginate(query, params)

    # Filter results based on permissions
    filtered_items = []
    for item in paginated_results.items:
        if check_memory_access_permissions(db, item, user):
            filtered_items.append(item)

    # Update paginated results with filtered items
    paginated_results.items = filtered_items
    paginated_results.total = len(filtered_items)

    return paginated_results


# Get all categories
@router.get("/categories")
@traced_endpoint("memories.categories")
async def get_categories(
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):    
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    
    # Get unique categories associated with the user's memories
    # Get all memories
    memories = db.query(Memory).filter(Memory.user_id == user.id, Memory.state != MemoryState.deleted, Memory.state != MemoryState.archived).all()
    # Get all categories from memories
    categories = [category for memory in memories for category in memory.categories]
    # Get unique categories
    unique_categories = list(set(categories))

    return {
        "categories": unique_categories,
        "total": len(unique_categories)
    }


class CreateMemoryRequest(BaseModel):    
    text: str
    metadata: dict = {}
    infer: bool = True
    app: str = "openmemory"


# Create new memory
@router.post("/")
@traced_endpoint("memories.create")
async def create_memory(
    request: CreateMemoryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.app_name", request.app)
    # Get or create app
    app_obj = db.query(App).filter(App.name == request.app,
                                   App.owner_id == user.id).first()
    if not app_obj:
        app_obj = App(name=request.app, owner_id=user.id)
        db.add(app_obj)
        db.commit()
        db.refresh(app_obj)

    # Check if app is active
    if not app_obj.is_active:
        raise HTTPException(status_code=403, detail=f"App {request.app} is currently paused on OpenMemory. Cannot create new memories.")

    # Log what we're about to do
    logging.info(f"Creating memory for user_id: {user.user_id} with app: {request.app}")
    
    # Try to get memory client safely
    try:
        memory_client = get_memory_client()
        if not memory_client:
            raise Exception("Memory client is not available")
    except Exception as client_error:
        logging.warning(f"Memory client unavailable: {client_error}. Creating memory in database only.")
        # Return a json response with the error
        return {
            "error": str(client_error)
        }

    # Try to save to Qdrant via memory_client
    try:
        metadata = {
            "source_app": "openmemory",
            "mcp_client": request.app,
            **(request.metadata or {}),
        }

        qdrant_response = memory_client.add(
            request.text,
            user_id=user.user_id,  # Use string user_id to match search
            metadata=metadata,
        )

        # Log the response for debugging
        logging.info(f"Qdrant response: {qdrant_response}")

        processed_results = []

        # Process Qdrant response
        if isinstance(qdrant_response, dict) and 'results' in qdrant_response:
            now_ts = datetime.now(UTC)
            for result in qdrant_response['results']:
                event_type = result.get('event')
                memory_id = UUID(result['id'])
                existing_memory = db.query(Memory).filter(Memory.id == memory_id).first()

                if event_type == 'ADD':
                    if existing_memory:
                        old_state = existing_memory.state
                        existing_memory.state = MemoryState.active
                        existing_memory.content = result['memory']
                        existing_memory.metadata_ = metadata
                    else:
                        memory_obj = Memory(
                            id=memory_id,
                            user_id=user.id,
                            app_id=app_obj.id,
                            content=result['memory'],
                            metadata_=metadata,
                            state=MemoryState.active,
                            created_at=now_ts,
                        )
                        db.add(memory_obj)
                        old_state = MemoryState.deleted

                    history = MemoryStatusHistory(
                        memory_id=memory_id,
                        changed_by=user.id,
                        old_state=old_state,
                        new_state=MemoryState.active,
                        changed_at=now_ts,
                    )
                    db.add(history)

                    processed_results.append({
                        "id": str(memory_id),
                        "event": event_type,
                        "memory": result.get("memory"),
                        "state": MemoryState.active.value,
                    })

                elif event_type == 'DELETE':
                    if existing_memory:
                        old_state = existing_memory.state
                        existing_memory.state = MemoryState.deleted
                        existing_memory.deleted_at = now_ts

                        history = MemoryStatusHistory(
                            memory_id=memory_id,
                            changed_by=user.id,
                            old_state=old_state,
                            new_state=MemoryState.deleted,
                            changed_at=now_ts,
                        )
                        db.add(history)

                        processed_results.append({
                            "id": str(memory_id),
                            "event": event_type,
                            "state": MemoryState.deleted.value,
                        })
                    else:
                        processed_results.append({
                            "id": str(memory_id),
                            "event": event_type,
                            "not_found": True,
                        })
                elif event_type == 'UPDATE':
                    if existing_memory:
                        old_state = existing_memory.state
                        # Update memory content and metadata
                        existing_memory.content = result.get('memory', existing_memory.content)
                        existing_memory.metadata_ = metadata
                        # Optionally update other fields if present in result
                        # existing_memory.state = MemoryState.active  # If state should be set to active on update
                        # existing_memory.updated_at = now_ts  # If you track update time

                        history = MemoryStatusHistory(
                            memory_id=memory_id,
                            changed_by=user.id,
                            old_state=old_state,
                            new_state=existing_memory.state,
                            changed_at=now_ts,
                        )
                        db.add(history)

                        processed_results.append({
                            "id": str(memory_id),
                            "event": event_type,
                            "memory": result.get("memory"),
                            "state": existing_memory.state.value,
                        })
            db.commit()
            return processed_results

        # If response is not the expected structure, just return it as-is
        db.commit()
        return qdrant_response
    except Exception as qdrant_error:
        logging.warning(f"Qdrant operation failed: {qdrant_error}.")
        raise ValueError(f"Failed to create memory: {qdrant_error}")        

# Get memory by ID
@router.get("/{memory_id}")
@traced_endpoint("memories.get")
async def get_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.memory_id", str(memory_id))
    memory = get_memory_or_404(db, memory_id, user)
    return {
        "id": memory.id,
        "text": memory.content,
        "created_at": int(memory.created_at.timestamp()),
        "state": memory.state.value,
        "app_id": memory.app_id,
        "app_name": memory.app.name if memory.app else None,
        "categories": [category.name for category in memory.categories],
        "metadata_": memory.metadata_
    }


class DeleteMemoriesRequest(BaseModel):
    memory_ids: List[UUID]
    user_id: str

# Delete multiple memories
@router.delete("/")
@traced_endpoint("memories.delete")
async def delete_memories(
    request: DeleteMemoriesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.deleted_count", len(request.memory_ids))
    for memory_id in request.memory_ids:
        update_memory_state(db, memory_id, MemoryState.deleted, user)
    return {"message": f"Successfully deleted {len(request.memory_ids)} memories"}


# Archive memories
@router.post("/actions/archive")
@traced_endpoint("memories.archive")
async def archive_memories(
    memory_ids: List[UUID],
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):    
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.archive_count", len(memory_ids))
    for memory_id in memory_ids:
        update_memory_state(db, memory_id, MemoryState.archived, user)
    return {"message": f"Successfully archived {len(memory_ids)} memories"}


class PauseMemoriesRequest(BaseModel):
    memory_ids: Optional[List[UUID]] = None
    category_ids: Optional[List[UUID]] = None
    app_id: Optional[UUID] = None
    all_for_app: bool = False
    global_pause: bool = False
    state: Optional[MemoryState] = None

# Pause access to memories
@router.post("/actions/pause")
@traced_endpoint("memories.pause")
async def pause_memories(
    request: PauseMemoriesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.global_pause", request.global_pause)
    if request.app_id:
        span.set_attribute("mem0.app_id", str(request.app_id))
    if request.memory_ids:
        span.set_attribute("mem0.memory_count", len(request.memory_ids))
    if request.category_ids:
        span.set_attribute("mem0.category_count", len(request.category_ids))
    user_id = user.id

    global_pause = request.global_pause
    all_for_app = request.all_for_app
    app_id = request.app_id
    memory_ids = request.memory_ids
    category_ids = request.category_ids
    state = request.state or MemoryState.paused

    
    if global_pause:
        # Pause all memories
        memories = db.query(Memory).filter(
            Memory.state != MemoryState.deleted,
            Memory.state != MemoryState.archived
        ).all()
        for memory in memories:
            update_memory_state(db, memory.id, state, user_id)
        return {"message": "Successfully paused all memories"}

    if app_id:
        # Pause all memories for an app
        memories = db.query(Memory).filter(
            Memory.app_id == app_id,
            Memory.user_id == user.id,
            Memory.state != MemoryState.deleted,
            Memory.state != MemoryState.archived
        ).all()
        for memory in memories:
            update_memory_state(db, memory.id, state, user)
        return {"message": f"Successfully paused all memories for app {app_id}"}
    
    if all_for_app and memory_ids:
        # Pause all memories for an app
        memories = db.query(Memory).filter(
            Memory.user_id == user.id,
            Memory.state != MemoryState.deleted,
            Memory.id.in_(memory_ids)
        ).all()
        for memory in memories:
            update_memory_state(db, memory.id, state, user)
        return {"message": f"Successfully paused all memories"}

    if memory_ids:
        # Pause specific memories
        for memory_id in memory_ids:
            update_memory_state(db, memory_id, state, user)
        return {"message": f"Successfully paused {len(memory_ids)} memories"}

    if category_ids:
        # Pause memories by category
        memories = db.query(Memory).join(Memory.categories).filter(
            Category.id.in_(category_ids),
            Memory.state != MemoryState.deleted,
            Memory.state != MemoryState.archived
        ).all()
        for memory in memories:
            update_memory_state(db, memory.id, state, user_id)
        return {"message": f"Successfully paused memories in {len(category_ids)} categories"}

    raise HTTPException(status_code=400, detail="Invalid pause request parameters")


# Get memory access logs
@router.get("/{memory_id}/access-log")
@traced_endpoint("memories.access_log")
async def get_memory_access_log(
    memory_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):    
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.memory_id", str(memory_id))
    span.set_attribute("mem0.page", page)
    span.set_attribute("mem0.page_size", page_size)
    query = db.query(MemoryAccessLog).filter(MemoryAccessLog.memory_id == memory_id)
    total = query.count()
    logs = query.order_by(MemoryAccessLog.accessed_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # Get app name
    for log in logs:
        app = db.query(App).filter(App.id == log.app_id).first()
        log.app_name = app.name if app else None

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": logs
    }


class UpdateMemoryRequest(BaseModel):
    memory_content: str

# Update a memory
@router.put("/{memory_id}")
@traced_endpoint("memories.update")
async def update_memory(
    memory_id: UUID,
    request: UpdateMemoryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):        
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.memory_id", str(memory_id))
    span.set_attribute("mem0.content_length", len(request.memory_content or ""))
    memory = get_memory_or_404(db, memory_id, user)
    memory.content = request.memory_content
    db.commit()
    db.refresh(memory)
    return memory

class FilterMemoriesRequest(BaseModel):
    page: int = 1
    size: int = 10
    search_query: Optional[str] = None
    app_ids: Optional[List[UUID]] = None
    category_ids: Optional[List[UUID]] = None
    sort_column: Optional[str] = None
    sort_direction: Optional[str] = None
    from_date: Optional[int] = None
    to_date: Optional[int] = None
    show_archived: Optional[bool] = False

@router.post("/filter", response_model=Page[MemoryResponse])
@traced_endpoint("memories.filter")
async def filter_memories(
    request: FilterMemoriesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.page", request.page)
    span.set_attribute("mem0.page_size", request.size)
    if request.search_query:
        span.set_attribute("mem0.search_query", request.search_query)
    user_id = user.id
    # Build base query
    query = db.query(Memory).filter(
        Memory.user_id == user.id,
        Memory.state != MemoryState.deleted,
    )

    # Filter archived memories based on show_archived parameter
    if not request.show_archived:
        query = query.filter(Memory.state != MemoryState.archived)

    # Apply search filter
    if request.search_query:
        query = query.filter(Memory.content.ilike(f"%{request.search_query}%"))

    # Apply app filter
    if request.app_ids:
        query = query.filter(Memory.app_id.in_(request.app_ids))

    # Add joins for app and categories
    query = query.outerjoin(App, Memory.app_id == App.id)

    # Apply category filter
    if request.category_ids:
        query = query.join(Memory.categories).filter(Category.id.in_(request.category_ids))
    else:
        query = query.outerjoin(Memory.categories)

    # Apply date filters
    if request.from_date:
        from_datetime = datetime.fromtimestamp(request.from_date, tz=UTC)
        query = query.filter(Memory.created_at >= from_datetime)

    if request.to_date:
        to_datetime = datetime.fromtimestamp(request.to_date, tz=UTC)
        query = query.filter(Memory.created_at <= to_datetime)

    # Apply sorting
    if request.sort_column and request.sort_direction:
        sort_direction = request.sort_direction.lower()
        if sort_direction not in ['asc', 'desc']:
            raise HTTPException(status_code=400, detail="Invalid sort direction")

        sort_mapping = {
            'memory': Memory.content,
            'app_name': App.name,
            'created_at': Memory.created_at
        }

        if request.sort_column not in sort_mapping:
            raise HTTPException(status_code=400, detail="Invalid sort column")

        sort_field = sort_mapping[request.sort_column]
        if sort_direction == 'desc':
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field.asc())
    else:
        # Default sorting
        query = query.order_by(Memory.created_at.desc())

    # Add eager loading for categories and make the query distinct
    query = query.options(
        joinedload(Memory.categories)
    ).distinct(Memory.id)

    # Use fastapi-pagination's paginate function
    return sqlalchemy_paginate(
        query,
        Params(page=request.page, size=request.size),
        transformer=lambda items: [
            MemoryResponse(
                id=memory.id,
                content=memory.content,
                created_at=memory.created_at,
                state=memory.state.value,
                app_id=memory.app_id,
                app_name=memory.app.name if memory.app else "openmemory",
                categories=[category.name for category in memory.categories],
                metadata_=memory.metadata_
            )
            for memory in items
        ]
    )


class SearchMemoriesRequest(BaseModel):
    query: str
    numberOfHits: int = 10
    page: int = 1
    filters: Optional[Union[dict, None]] = None
    

# Search memories endpoint
@router.post("/search")
@traced_endpoint("memories.search")
async def search_memories_endpoint(
    request: SearchMemoriesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    """
    Search memories using vector similarity search.
    
    This endpoint accepts the same parameters as the MCP search_memory function
    and uses the reusable search logic from memory_client.py.
    """
    
    # Default app for API requests
    app_id = "openmemory"
    
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.query", request.query)
    span.set_attribute("mem0.page", request.page)
    span.set_attribute("mem0.limit", request.numberOfHits)

    try:
        # Use the reusable search function
        memories = await search_memories(
            query=request.query,
            user_id=user.user_id,
            app_id=app_id,
            numberOfHits=request.numberOfHits,
            page=request.page,
            filters=request.filters
        )
        
        # Log memory access
        await log_memory_access(
            memories=memories,
            user_id=user.user_id,
            app_id=app_id,
            query=request.query,
            access_type="search"
        )
        
        return {
            "results": memories,
            "query": request.query,
            "page": request.page,
            "total": len(memories)
        }
    except Exception as e:
        logging.exception(f"Error in search endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/{memory_id}/related", response_model=Page[MemoryResponse])
@traced_endpoint("memories.related")
async def get_related_memories(
    memory_id: UUID,
    params: Params = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.memory_id", str(memory_id))
    user_id = user.user_id

    # Get the source memory
    memory = get_memory_or_404(db, memory_id, user)
    
    # Extract category IDs from the source memory
    category_ids = [category.id for category in memory.categories]
    
    if not category_ids:
        return Page.create([], total=0, params=params)
    
    # Build query for related memories
    query = db.query(Memory).distinct(Memory.id).filter(
        Memory.user_id == user.id,
        Memory.id != memory_id,
        Memory.state != MemoryState.deleted
    ).join(Memory.categories).filter(
        Category.id.in_(category_ids)
    ).options(
        joinedload(Memory.categories),
        joinedload(Memory.app)
    ).order_by(
        func.count(Category.id).desc(),
        Memory.created_at.desc()
    ).group_by(Memory.id)
    
    # ⚡ Force page size to be 5
    params = Params(page=params.page, size=5)
    
    return sqlalchemy_paginate(
        query,
        params,
        transformer=lambda items: [
            MemoryResponse(
                id=memory.id,
                content=memory.content,
                created_at=memory.created_at,
                state=memory.state.value,
                app_id=memory.app_id,
                app_name=memory.app.name if memory.app else "openmemory",
                categories=[category.name for category in memory.categories],
                metadata_=memory.metadata_
            )
            for memory in items
        ]
    )
