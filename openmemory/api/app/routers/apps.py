from typing import Optional
import datetime
from uuid import UUID
from functools import wraps
from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, sql

from app.database import get_db
from app.models import User, App, Memory, MemoryAccessLog, MemoryState
from app.auth import get_current_user, get_user_record
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

router = APIRouter(prefix="/api/v1/apps", tags=["apps"])

_TRACER = trace.get_tracer("mem0.api.apps")


def _record_exception(span, exc: Exception) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def traced_endpoint(span_name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with _TRACER.start_as_current_span(span_name, kind=SpanKind.SERVER) as span:
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    _record_exception(span, exc)
                    raise

        return wrapper

    return decorator

# Helper functions
def get_app_or_404(db: Session, app_id: UUID) -> App:
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app

# List all apps with filtering
@router.get("/")
@traced_endpoint("apps.list")
async def list_apps(
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = 'name',
    sort_direction: str = 'asc',
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    span = trace.get_current_span()
    if name:
        span.set_attribute("mem0.app_name_query", name)
    span.set_attribute("mem0.is_active_filter", is_active if is_active is not None else "any")
    span.set_attribute("mem0.page", page)
    span.set_attribute("mem0.page_size", page_size)
    # Create a subquery for memory counts
    memory_counts = db.query(
        Memory.app_id,
        func.count(Memory.id).label('memory_count')
    ).filter(
        Memory.state.in_([MemoryState.active, MemoryState.paused, MemoryState.archived])
    ).group_by(Memory.app_id).subquery()

    # Create a subquery for access counts
    access_counts = db.query(
        MemoryAccessLog.app_id,
        func.count(func.distinct(MemoryAccessLog.memory_id)).label('access_count')
    ).group_by(MemoryAccessLog.app_id).subquery()

    # Base query
    query = db.query(
        App,
        func.coalesce(memory_counts.c.memory_count, 0).label('total_memories_created'),
        func.coalesce(access_counts.c.access_count, 0).label('total_memories_accessed')
    )

    # Join with subqueries
    query = query.outerjoin(
        memory_counts,
        App.id == memory_counts.c.app_id
    ).outerjoin(
        access_counts,
        App.id == access_counts.c.app_id
    )

    if name:
        query = query.filter(App.name.ilike(f"%{name}%"))

    if is_active is not None:
        query = query.filter(App.is_active == is_active)

    # Apply sorting
    if sort_by == 'name':
        sort_field = App.name
    elif sort_by == 'memories':
        sort_field = func.coalesce(memory_counts.c.memory_count, 0)
    elif sort_by == 'memories_accessed':
        sort_field = func.coalesce(access_counts.c.access_count, 0)
    else:
        sort_field = App.name  # default sort

    if sort_direction == 'desc':
        query = query.order_by(desc(sort_field))
    else:
        query = query.order_by(sort_field)

    total = query.count()
    apps = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "apps": [
            {
                "id": app[0].id,
                "name": app[0].name,
                "is_active": app[0].is_active,
                "total_memories_created": app[1],
                "total_memories_accessed": app[2]
            }
            for app in apps
        ]
    }

# Get app details
@router.get("/{app_id}")
@traced_endpoint("apps.details")
async def get_app_details(
    app_id: UUID,
    db: Session = Depends(get_db)
) -> dict:
    span = trace.get_current_span()
    span.set_attribute("mem0.app_id", str(app_id))
    app = get_app_or_404(db, app_id)

    # Get memory access statistics
    access_stats = db.query(
        func.count(MemoryAccessLog.id).label("total_memories_accessed"),
        func.min(MemoryAccessLog.accessed_at).label("first_accessed"),
        func.max(MemoryAccessLog.accessed_at).label("last_accessed")
    ).filter(MemoryAccessLog.app_id == app_id).first()

    return {
        "is_active": app.is_active,
        "total_memories_created": db.query(Memory)
            .filter(Memory.app_id == app_id)
            .count(),
        "total_memories_accessed": access_stats.total_memories_accessed or 0, # type: ignore
        "first_accessed": access_stats.first_accessed, # type: ignore
        "last_accessed": access_stats.last_accessed # type: ignore
    }

# List memories created by app
@router.get("/{app_id}/memories")
@traced_endpoint("apps.memories")
async def list_app_memories(
    app_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.app_id", str(app_id))
    span.set_attribute("mem0.page", page)
    span.set_attribute("mem0.page_size", page_size)
    get_app_or_404(db, app_id)
    query = db.query(Memory).filter(
        Memory.app_id == app_id,
        Memory.state.in_([MemoryState.active, MemoryState.paused, MemoryState.archived])
    )
    # Add eager loading for categories
    query = query.options(joinedload(Memory.categories))
    total = query.count()
    memories = query.order_by(Memory.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "memories": [
            {
                "id": memory.id,
                "content": memory.content,
                "created_at": memory.created_at,
                "state": memory.state.value,
                "app_id": memory.app_id,
                "categories": [category.name for category in memory.categories],
                "metadata_": memory.metadata_
            }
            for memory in memories
        ]
    }

# List memories accessed by app
@router.get("/{app_id}/accessed")
@traced_endpoint("apps.accessed")
async def list_app_accessed_memories(
    app_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.app_id", str(app_id))
    span.set_attribute("mem0.page", page)
    span.set_attribute("mem0.page_size", page_size)
    
    # Get memories with access counts
    query = db.query(
        Memory,
        func.count(MemoryAccessLog.id).label("access_count")
    ).join(
        MemoryAccessLog,
        Memory.id == MemoryAccessLog.memory_id
    ).filter(
        MemoryAccessLog.app_id == app_id
    ).group_by(
        Memory.id
    ).order_by(
        desc("access_count")
    )

    # Add eager loading for categories
    query = query.options(joinedload(Memory.categories))

    total = query.count()
    results = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "memories": [
            {
                "memory": {
                    "id": memory.id,
                    "content": memory.content,
                    "created_at": memory.created_at,
                    "state": memory.state.value,
                    "app_id": memory.app_id,
                    "app_name": memory.app.name if memory.app else None,
                    "categories": [category.name for category in memory.categories],
                    "metadata_": memory.metadata_
                },
                "access_count": count
            }
            for memory, count in results
        ]
    }


@router.put("/{app_id}")
@traced_endpoint("apps.update")
async def update_app_details(
    app_id: UUID,
    is_active: bool,
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.app_id", str(app_id))
    span.set_attribute("mem0.is_active", is_active)
    app = get_app_or_404(db, app_id)
    app.is_active = is_active # type: ignore
    if (description is not None):
        app.description = description # type: ignore
    if (metadata is not None):        
        if not isinstance(metadata, dict):
            raise HTTPException(status_code=400, detail="Metadata must be a dictionary")
        existing_metadata = app.metadata_ if app.metadata_ is not None else {}
        app.metadata_ = {**existing_metadata, **metadata} # type: ignore        
    app.updated_at = datetime.datetime.now(datetime.timezone.utc) # type: ignore
    db.commit()
    return {"status": "success", "message": "Updated app details successfully"}

@router.post("/")
@traced_endpoint("apps.create")
async def create_app(
    name: str,
    description: Optional[str] = None,
    is_active: bool = True,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    span = trace.get_current_span()
    span.set_attribute("mem0.user_id", user.user_id)
    span.set_attribute("mem0.app_name", name)
    span.set_attribute("mem0.is_active", is_active)
    # Validate input
    if not name:
        raise HTTPException(status_code=400, detail="App name cannot be empty")
    # Use the authenticated user as the owner
    userId = user.id
    # Make sure we don't already have an app with this name
    existing_app = db.execute(
        sql.select(App.id).where(App.name == name, App.owner_id == userId)
    ).scalars().first()
    if existing_app:
        raise HTTPException(status_code=400, detail="App with this name already exists")
    # Create new record
    new_app = App(
        name=name, 
        is_active=is_active,
        owner_id=userId,
        description=description,
        metadata_= metadata or {},
        created_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(new_app)
    db.commit()
    db.refresh(new_app)

    return {"status": "success", "message": "App created successfully", "app_id": new_app.id, "data": new_app }