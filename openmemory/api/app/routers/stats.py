from app.utils.client_config_factory import get_parsed_memory_config
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging
from app.database import get_db
from app.models import User, Memory, App, MemoryState, GraphHealthDetails, GraphHealthStatus
from app.utils.memory import get_memory_client
from typing import Optional
from fastapi import Depends
from mem0.utils.factory import VectorStoreFactory
import mem0
from mem0.configs.base import MemoryConfig
from datetime import datetime, timezone
from app.auth import get_current_user, get_user_record, check_auth_service_health
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

_TRACER = trace.get_tracer("mem0.api.stats")


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
                    # try to attach user if present
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
router = APIRouter(prefix="/api/v1/stats", tags=["stats"])
healthcheck_user = "system_healthcheck"

@router.get("/")
@traced_endpoint("stats.get_profile")
async def get_profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_user_record)
):
    
    # Get total number of memories
    total_memories = db.query(Memory).filter(Memory.user_id == user.id, Memory.state != MemoryState.deleted).count()

    # Get total number of apps
    apps = db.query(App).filter(App.owner_id == user.id)
    total_apps = apps.count()

    return {
        "total_memories": total_memories,
        "total_apps": total_apps,
        "apps": apps.all()
    }


def safe_get_config():
    """
    Helper function to safely get the memory client configuration.
    Returns an empty dictionary if an error occurs.
    """
    try:
        parsedConfig = get_parsed_memory_config()
        if isinstance(parsedConfig, dict):
            return parsedConfig
        else:
            raise ValueError("Parsed configuration is not a dictionary.")        
    except Exception as e:
        logger.error(f"Error getting memory client config: {e}")        
        return { "error": str(e) }    

def _safe_check_config(config: dict, key: str) -> bool:
    """
    Helper function to safely check if a key exists in the configuration.
    Returns False if the key does not exist or if an error occurs.
    """
    try:
        return key in config and config[key] is not None
    except Exception as e:        
        return False

def get_mem0_build_info(verbose: bool = False) -> dict:
    """
    Get mem0 build information for health check responses.
    
    Args:
        verbose: If True, include detailed build information
        
    Returns:
        Dictionary containing mem0 build information
    """
    try:
        build_info = mem0.__build_info__
        
        mem0_info = {
            "version": mem0.__version__,
            "build_type": build_info['type'],
            "build_info": build_info.get('info', 'unknown')
        }
        
        # Add detailed CI/CD information if available
        if build_info['type'] == 'distribution_build':
            mem0_info["ci_metadata"] = {
                "commit": build_info.get('commit'),
                "run_id": build_info.get('run_id'), 
                "build_timestamp": build_info.get('timestamp')
            }
        
        # Add verbose details if requested
        if verbose:
            mem0_info["verbose"] = {
                "mem0_version": mem0.__version__,
                "build_details": build_info,
                "build_stamp": getattr(mem0, '__build_stamp__', 'not available')
            }
        
        return mem0_info
        
    except Exception as e:
        logger.error(f"Error getting mem0 build info: {e}")
        return {
            "version": "unknown",
            "build_type": "unknown", 
            "build_info": f"error: {str(e)}"
        }
    

@router.get("/health-check")
async def health_check(
    strict: bool = True, 
    verbose: int = Query(0, description="Include verbose mem0 build information (1 for verbose)"),
    db: Optional[Session] = Depends(get_db)
): 
    """
    Health check endpoint to verify the API is running.
    @param strict: If True (the default), health check will fail if any critical service is down.
    @param verbose: If 1, include detailed mem0 build information in response.
    """

    client_active: bool = False
    vector_store_available: bool = False
    vector_enabled: bool = False
    graph_store_available: bool = False
    history_store_available: bool = False
    system_db_available: bool = False
    graph_enabled: bool = False
    errors = []
    config = safe_get_config()
    if ("error" in config):
        errors.append(f"Configuration error: {config['error']}")
        raise HTTPException(
                status_code=503,
                detail={
                    "error": "Service is not fully operational - configuration data not found.",
                    "code": 503,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "service": "openmemory-api",
                    "mem0": get_mem0_build_info(verbose == 1),
                    "details": {
                        "config_present": False, 
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
    try:
        # Check if system / history database is available        
        if db is not None:
            try:
                db.query(User).first()
                db.close()
                system_db_available = True
            except Exception as e:
                logger.error(f"System Database connection error: {str(e)}")
                system_db_available = False                
                errors.append(f"System Database connection error")
        else:
            system_db_available = False
            errors.append("System Database dependency not provided.")            
            
        vectorProvider = None
        graphProvider = None
        # Check if memory client is available
        try:
            mem_client = get_memory_client()
            if mem_client is None:
                errors.append("Memory client is not available.")                
            else:
                client_active = True
                # If the memory client was able to initialize we can pull what we need from it
                vectorProvider = mem_client.vector_store if hasattr(mem_client, 'vector_store') else None
                graphProvider = mem_client.graph if hasattr(mem_client, 'graph') else None
        except Exception as e:
            logger.error(f"Memory client connection error: {str(e)}")
            errors.append(f"Memory client connection error: {str(e)}")

        # Check if vector store is available
        if _safe_check_config(config, "vector_store"):
            try:
                vs_buffer = config["vector_store"]
                if isinstance(vs_buffer, dict):
                    vector_store_section: dict = vs_buffer
                    provider = vector_store_section.get("provider", None)
                    if provider is not None:
                        vector_enabled = True
                        if vectorProvider is None:                            
                            vectorConfig = vector_store_section.get("config", {})
                            vectorProvider = VectorStoreFactory.create(provider, vectorConfig)
                        vector_store_available = vectorProvider is not None and vectorProvider.conn is not None
            except Exception as e:
                logger.error(f"Vector Store connection error: {str(e)}")
                errors.append(f"Vector Store connection error: {str(e.__cause__)}")
        
        # Check if graph store is available
        if _safe_check_config(config, "graph_store"):
            try:
                gs_buffer = config["graph_store"]
                if isinstance(gs_buffer, dict):
                    graph_store_section: dict = gs_buffer
                    provider = graph_store_section.get("provider", None)
                    if provider is not None:
                        graph_enabled = True
                        if graphProvider is None:
                            from mem0.memory.graph_memory import MemoryGraph
                            graphProvider = MemoryGraph(MemoryConfig(**config))
                        graph_store_available = graphProvider is not None
            except Exception as e:
                logger.error(f"Graph Store connection error: {str(e)}")
                errors.append(f"Graph Store connection error: {str(e.__cause__)}")        
        
    except Exception as e:
       errors.append(f"Unexpected error during health check: {str(e)}")
    finally:
        if db is not None:
            db.close()
    # I'm not sure I know the difference between system_db_available and history_store_available
    history_store_available = system_db_available
    # Determine if we return an overall success or failure
    isOk = True
    if not client_active or not system_db_available or not history_store_available:
        isOk = False
        errors.append("One or more critical services are not available.")
    if strict and isOk:
        if vector_enabled and not vector_store_available:
            isOk = False
            errors.append("Vector store is not available.")
        if graph_enabled and not graph_store_available:
            isOk = False
            errors.append("Graph store is not available.")            

    if not isOk:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service is not fully operational.",
                "code": 503,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service": "openmemory-api",
                "mem0": get_mem0_build_info(verbose == 1),
                "details": {
                    "client_active": client_active,
                    "system_db_available": system_db_available,
                    "vector_enabled": vector_enabled,
                    "vector_store_available": vector_store_available,
                    "graph_enabled": graph_enabled,
                    "graph_store_available": graph_store_available,
                    "history_store_available": history_store_available,
                    "errors": errors
                }
            }
        )
    # Check authentication service health
    auth_health = check_auth_service_health()
    
    # And send all this data back
    return {
        "status": "ok", 
        "message": "API is running smoothly.", 
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "openmemory-api",
        "mem0": get_mem0_build_info(verbose == 1),
        "details": {
            "client_active": client_active,
            "system_db_available": system_db_available,
            "vector_enabled": vector_enabled,
            "vector_store_available": vector_store_available,
            "graph_enabled": graph_enabled,        
            "graph_store_available": graph_store_available,
            "history_store_available": history_store_available,
            "auth_service": auth_health,
            "errors": errors
        }
    }

@router.get(
    "/health-check/graph",
    responses={
        200: {
            "description": "Graph health status",
            "content": {
                "application/json": {
                    "schema": {
                        "title": "GraphHealthStatus",
                        "type": "object",
                        "properties": {
                            "online": {"type": "boolean"},
                            "can_add": {"type": "boolean"},
                            "can_search": {"type": "boolean"},
                            "can_delete": {"type": "boolean"},
                            "details": {
                                "title": "GraphHealthDetails",
                                "type": "object",
                                "properties": {
                                    "errors": {"type": "array", "items": {"type": "string"}},
                                    "timestamp": {"type": "string"},
                                    "add_result": {"nullable": True},
                                    "search_result": {"nullable": True},
                                },
                                "required": ["errors", "timestamp"],
                            },
                        },
                        "required": ["online", "can_add", "can_search", "can_delete", "details"],
                    }
                }
            },
        },
        422: {
            "description": "Graph health check error",
            "content": {
                "application/json": {
                    "schema": {
                        "title": "GraphHealthErrorResponse",
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "loc": {"type": "array", "items": {"type": "string"}},
                                        "msg": {"type": "string"},
                                        "type": {"type": "string"},
                                    },
                                    "required": ["loc", "msg", "type"],
                                },
                            }
                        },
                        "required": ["detail"],
                    }
                }
            },
        },
    },
)
async def graph_health_check() -> "GraphHealthStatus":
    """
    Graph memory health check endpoint to verify graph store functionality.
    Returns status of graph connectivity and basic operations (add, search, delete).
    """
    try:
        # Initialize response structure
        health_status = GraphHealthStatus(
            online=False,
            can_add=False,
            can_search=False,
            can_delete=False,
            details=GraphHealthDetails(
                errors=[],
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

        # Step 1: Check if graph client is available
        try:
            memory_client = get_memory_client()
            if memory_client is None:
                health_status.details.errors.append("Memory client is not available")
                return health_status

            graph_client = getattr(memory_client, "graph", None)
            if graph_client is None:
                health_status.details.errors.append("Graph client is not available on memory client")
                return health_status

            health_status.online = True

        except Exception as e:
            health_status.details.errors.append(f"Failed to get graph client: {str(e)}")
            return health_status

        # Prepare test data and filters
        test_data = "Health check test: John likes apples and Mary likes oranges."
        filters = {"user_id": healthcheck_user}

        # Step 2: Test add functionality
        try:
            add_result = graph_client.add(test_data, filters)
            health_status.can_add = True
            health_status.details.add_result = add_result
        except Exception as e:
            health_status.details.errors.append(f"Add operation failed: {str(e)}")

        # Step 3: Test search functionality
        try:
            search_result = graph_client.search("John likes apples", filters)
            if health_status.can_add:
                health_status.can_search = bool(search_result)
            else:
                health_status.can_search = True
            health_status.details.search_result = search_result
        except Exception as e:
            health_status.details.errors.append(f"Search operation failed: {str(e)}")

        # Step 4: Test delete functionality
        try:
            graph_client.delete_all(filters)
            health_status.can_delete = True
        except Exception as e:
            health_status.details.errors.append(f"Delete operation failed: {str(e)}")

        return health_status

    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["graph_health_check"],
                    "msg": f"Unexpected error during graph health check: {str(e)}",
                    "type": "graph_health_error",
                }
            ],
        )

