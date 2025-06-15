from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Memory, App, MemoryState
from app.utils.memory import get_memory_client
from typing import Optional
from fastapi import Depends

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])

@router.get("/")
async def get_profile(
    user_id: str,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get total number of memories
    total_memories = db.query(Memory).filter(Memory.user_id == user.id, Memory.state != MemoryState.deleted).count()

    # Get total number of apps
    apps = db.query(App).filter(App.owner == user)
    total_apps = apps.count()

    return {
        "total_memories": total_memories,
        "total_apps": total_apps,
        "apps": apps.all()
    }

@router.get("/health-check")
async def health_check(strict: bool = True, db: Optional[Session] = Depends(get_db)): 
    """
    Health check endpoint to verify the API is running.
    @param strict: If True (the default), health check will fail if any critical service is down.
    """

    client_active: bool = False
    vector_store_available: bool = False
    graph_store_available: bool = False
    history_store_available: bool = False
    system_db_available: bool = False
    graph_enabled: bool = False
    errors = []
    
    try:
        # Check if system / history database is available        
        if db is not None:
            try:
                db.query(User).first()
                db.close()
                system_db_available = True
            except Exception as e:
                errors.append(f"System Database connection error: {str(e)}")                            
        else:
            errors.append("System Database dependency not provided.")            

        try:
            mem_client = get_memory_client()
            if mem_client is not None:
                client_active = True

                config = mem_client["config"]

                if config is None:
                    errors.append("Memory client configuration is not available.")
                else:
                    vector_store_available = "vector_store" in config and config["vector_store"] is not None
                    graph_store_available =  "graph_store" in config and config["graph_store"] is not None
                    graph_enabled = "enable_graph" in config and config["enable_graph"]                                
            else:
                errors.append("Memory client is not available.")                
        except Exception as e:
            errors.append(f"Memory client connection error: {str(e)}")
        
    except Exception as e:
       errors.append(f"Unexpected error during health check: {str(e)}")
    finally:
        if db is not None:
            db.close()
    # I'm not sure I know the difference between system_db_available and history_store_available
    history_store_available = system_db_available

    if strict and not (client_active and system_db_available and history_store_available):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service is not fully operational.",
                "code": 503,
                "details": {
                    "client_active": client_active,
                    "system_db_available": system_db_available,
                    "vector_store_available": vector_store_available,
                    "graph_store_available": graph_store_available,
                    "history_store_available": history_store_available,
                    "graph_enabled": graph_enabled,
                    "errors": errors
                }
            }
        )
    
    import logging
    logger = logging.getLogger(__name__)
    for error in errors:
        logger.error(error)
    return {"status": "ok", "message": "API is running smoothly.", "details": {
        "client_active": client_active,
        "system_db_available": system_db_available,
        "vector_store_available": vector_store_available,
        "graph_store_available": graph_store_available,
        "history_store_available": history_store_available,
        "graph_enabled": graph_enabled,
        "errors": ["Some errors occurred. Please contact support."]
    }}
