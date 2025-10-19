from typing import Optional
import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import String, Uuid, func, desc, sql

from app.database import get_db
from app.models import User, App, Memory, MemoryAccessLog, MemoryState
from app.auth import get_current_user, get_user_id, get_user_record, require_admin
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

_TRACER = trace.get_tracer("mem0.api.users")


def _record_exception(span, exc: Exception) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def traced_endpoint(span_name: str):
    def decorator(func):
        from functools import wraps

        @wraps(func)
        async def wrapper(*args, **kwargs):
            with _TRACER.start_as_current_span(span_name, kind=SpanKind.SERVER) as span:
                try:
                    user = kwargs.get("user")
                    if not user:
                        for a in args:
                            if hasattr(a, "user_id"):
                                user = a
                                break
                    if user and hasattr(user, "user_id"):
                        span.set_attribute("mem0.user_id", getattr(user, "user_id"))
                    return await func(*args, **kwargs)
                except Exception as exc:
                    _record_exception(span, exc)
                    raise

        return wrapper

    return decorator

DEFAULT_USER_ID="beae98e4-fda0-4531-9119-889ffcb469fe"
router = APIRouter(prefix="/api/v1/users", tags=["users"])

# Helper functions
def get_user_or_404(db: Session, user_id: str | UUID) -> App:        
    if isinstance(user_id, UUID):
        user = db.query(User).filter(User.id == user_id).first()
    else:
        # TODO: Would be nice to have passthrough conversion for string to UUID
        user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# List all users with filtering - lets wait until API keys are in place for this
@router.get("/")
@traced_endpoint("users.list")
async def list_users(
    #name: Optional[str] = None,
    #is_active: Optional[bool] = None,
    #sort_by: str = 'name',
    #sort_direction: str = 'asc',
    #page: int = Query(1, ge=1),
    #page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    require_admin()
    #raise HTTPException(status_code=501, detail="This endpoint is not implemented yet")
    return db.query(User).all()

# Get app details
@router.get("/{user_id}")
@traced_endpoint("users.get")
async def get_user_details(
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    if not user_id == user.user_id:
        require_admin()
    user = get_user_or_404(db, user_id)

    # Get memory access statistics
    apps = db.query(App).filter(App.owner_id == user.id).options(joinedload(App.memories)).all()
    return {
        "is_active": user.is_active,
        "total_memories_created": user.memories.count(user.memories),
        "name": user.name,
        "description": user.description,
        "created_at": user.created_at,
        "apps": [
            {
                "id": app.id,
                "name": app.name,
                "is_active": app.is_active,
                "created_at": app.created_at,
                "updated_at": app.updated_at,                
            }
            for app in apps
        ]
    }

@router.post("/")
@traced_endpoint("users.create")
async def create_user(
    user_id: str,
    name: str = "",    
    email: Optional[str] = None,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):    
    require_admin()
    # Validate input
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID cannot be empty")
    # Check if user exists
    # Check if user exists and retrieve id
    db_user_id = db.execute(
        sql.select(User.id).where(User.user_id == user_id)
    ).scalars().first()
    if db_user_id:
        raise HTTPException(status_code=409, detail="User already exists")
    # Create record
    new_user = User(
        name=name, 
        email=email,
        user_id=user_id,
        metadata_= metadata or {},
        created_at=datetime.datetime.now(datetime.UTC),
        updated_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"status": "success", "message": "User created successfully", "user_id": new_user.id, "data": new_user}

@router.put("/")
@traced_endpoint("users.edit")
async def edit_user(
    user_id: str,
    name: Optional[str] = None,    
    email: Optional[str] = None,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    if not user_id == user.user_id:
        require_admin()
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID cannot be empty")
    # Check if user exists
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Username not found")
    # Update user fields
    if name is not None:
        user.name = name # type: ignore
    if email is not None:
        user.email = email # type: ignore
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise HTTPException(status_code=400, detail="Metadata must be a dictionary")
        user.metadata_ = {**(user.metadata_ or {}), **metadata} # type: ignore
    user.updated_at = datetime.datetime.now(datetime.UTC)         # type: ignore
    # commit changes
    db.commit()
    db.refresh(user)

    return {"status": "success", "message": "User updated successfully", "id": user.id, "data": user}



@router.delete("/{user_id}")
@traced_endpoint("users.delete")
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    if not user_id == user.user_id:
        require_admin()
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID cannot be empty")    
    user = db.query(User).filter(User.user_id == user_id).first()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
        
    for app in user.apps:
        db.delete(app)
    db.commit()
    
    db.delete(user)
    db.commit()
    return {"status": "success", "message": "User deleted successfully"}