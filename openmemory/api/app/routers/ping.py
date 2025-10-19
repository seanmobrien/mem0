from app.utils.client_config_factory import get_parsed_memory_config
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging
from app.database import get_db
from app.models import User, Memory, App, MemoryState, GraphHealthDetails, GraphHealthStatus
from app.utils.memory import get_memory_client
from typing import Optional
from mem0.utils.factory import VectorStoreFactory
import mem0
from datetime import datetime, timezone
from app.auth import get_current_user, get_user_record, check_auth_service_health
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

_TRACER = trace.get_tracer("mem0.api.ping")


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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ping", tags=["ping"])

@router.get("/")
@traced_endpoint("ping.get")
async def get_ping(
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record),
    projectName: Optional[str] = Query(None, description="Filter projects by name"),
    projectId: Optional[str] = Query(None, description="Filter projects by ID")
):
    """Ping endpoint to check service health and return user info with projects"""
    # Query user's apps with memory counts
    from sqlalchemy import func
    apps_query = db.query(
        App.id,
        App.name,
        App.description,
        func.count(Memory.id).label('memory_count')
    ).filter(
        App.owner_id == user.id,
        App.is_active == True
    ).outerjoin(
        Memory, (Memory.app_id == App.id) & (Memory.state == MemoryState.active)
    ).group_by(App.id, App.name, App.description)
    
    # Apply filters if provided
    if projectId:
        apps_query = apps_query.filter(App.id == projectId)
    if projectName:
        apps_query = apps_query.filter(App.name.ilike(f"%{projectName}%"))
    
    apps_with_counts = apps_query.all()
    
    # Convert to projects list
    projects = [
        {
            "id": str(app.id),
            "name": app.name,
            "description": app.description,
            "memory_count": app.memory_count
        }
        for app in apps_with_counts
    ]
    
    # Select the project: specified one or the one with most memories
    selected_project = None
    selected_project_id = None
    selected_project_name = None
    
    if projects:
        if projectId:
            # Use the specified project ID if it exists in results
            selected_app = next((p for p in projects if p["id"] == projectId), None)
            if selected_app:
                selected_project = selected_app
        elif projectName:
            # Use the first match if filtering by name
            selected_project = projects[0]
        else:
            # Use the project with most memories
            selected_project = max(projects, key=lambda x: x["memory_count"])
        
        if selected_project:
            selected_project_id = selected_project["id"]
            selected_project_name = selected_project["name"]
    
    return {
        "name": user.name,
        "email": user.email,
        "user_id": user.user_id,
        "projectId": selected_project_id,
        "projectName": selected_project_name,
        "projects": projects
    }
