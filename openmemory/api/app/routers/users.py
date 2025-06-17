from typing import Optional
import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import String, Uuid, func, desc

from app.database import get_db
from app.models import User, App, Memory, MemoryAccessLog, MemoryState

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
async def list_users(
    #name: Optional[str] = None,
    #is_active: Optional[bool] = None,
    #sort_by: str = 'name',
    #sort_direction: str = 'asc',
    #page: int = Query(1, ge=1),
    #page_size: int = Query(10, ge=1, le=100),
    #db: Session = Depends(get_db)
):
    raise HTTPException(status_code=501, detail="This endpoint is not implemented yet")

# Get app details
@router.get("/{user_id}")
async def get_user_details(
    user_id: str,
    db: Session = Depends(get_db)
):
    user = get_user_or_404(db, user_id)

    # Get memory access statistics
    apps = db.query(App).filter(App.owner_id == user.id).options(joinedload(App.memories)).all()
    return {
        "is_active": user.is_active,
        "total_memories_created": user.memories.count(),
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
async def create_user(
    user_id: str,
    name: str = "",
    is_active: bool = True,
    db: Session = Depends(get_db)
):
    # Validate input
    if not user_id:
        raise HTTPException(status_code=400, detail="App name cannot be empty")
    # Check if user exists
    user = db.query(User).filter(User.user_id == user_id or User.id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Username already exists")
    # Check if app with this name already exists    
    new_user = User(
        name=name, 
        is_active=is_active,
        user_id=user_id,
        owner_id=user.id,
        created_at=datetime.datetime.now(datetime.UTC),
        updated_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"status": "success", "message": "User created successfully", "app_id": new_user.id, "data": new_user}
