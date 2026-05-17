from typing import Optional, Set
from uuid import UUID
from sqlalchemy.orm import Session
from app.models import Memory, App, MemoryState, User, AccessControl


def get_accessible_memory_ids(db: Session, app_id: UUID, user: User) -> Optional[Set[UUID]]:
    """
    Get the set of memory IDs that the app has access to based on app-level ACL rules.
    Returns None when all memories are accessible.
    """
    app_access = db.query(AccessControl).filter(
        AccessControl.subject_type == "app",
        AccessControl.subject_id == app_id,
        AccessControl.object_type == "memory"
    ).all()

    if not app_access:
        return None

    allowed_memory_ids = set()
    denied_memory_ids = set()

    for rule in app_access:
        if rule.effect == "allow":
            if rule.object_id:
                allowed_memory_ids.add(rule.object_id)
            else:
                return None
        elif rule.effect == "deny":
            if rule.object_id:
                denied_memory_ids.add(rule.object_id)
            else:
                return set()

    if allowed_memory_ids:
        allowed_memory_ids -= denied_memory_ids

    return allowed_memory_ids


def check_memory_access_permissions(
    db: Session,
    memory: Memory,
    user: User,
    app_id: Optional[UUID] = None
) -> bool:
    """
    Check if the given app has permission to access a memory based on:
    1. Memory state (must be active)
    2. App state (must not be paused)
    3. App-specific access controls

    Args:
        db: Database session
        memory: Memory object to check access for
        app_id: Optional app ID to check permissions for

    Returns:
        bool: True if access is allowed, False otherwise
    """
    # Check if memory is active
    if memory.state != MemoryState.active:
        return False

    # If no app_id provided, only check memory state
    if not app_id:
        return True

    # Check if app exists and is active
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        return False

    # Check if app is paused/inactive
    if not app.is_active:
        return False

    # Check app-specific access controls
    accessible_memory_ids = get_accessible_memory_ids(db, app_id, user)

    # If accessible_memory_ids is None, all memories are accessible
    if accessible_memory_ids is None:
        return True

    # Check if memory is in the accessible set
    return memory.id in accessible_memory_ids
