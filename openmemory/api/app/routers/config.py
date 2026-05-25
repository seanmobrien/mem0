from typing import Dict, Any, Optional
from app.utils.client_config_factory import split_config
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import logging
from app.database import get_db
from app.models import Config as ConfigModel
from app.utils.memory import reset_memory_client
from app.auth import get_current_user, get_user_record, optional_auth
from app.auth import require_admin
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

_TRACER = trace.get_tracer("mem0.api.config")


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

router = APIRouter(prefix="/api/v1/config", tags=["config"])

class LLMKwargsAzure(BaseModel): 
    api_key: Optional[str] = None
    azure_deployment: Optional[str] = None
    azure_endpoint: Optional[str] = None
    api_version: Optional[str] = None
    default_headers: Optional[Dict[str, str]] = None
    
class LLMConfig(BaseModel):
    model: str = Field(..., description="LLM model name")
    temperature: Optional[float | str] = None
    max_tokens: Optional[int| str] = None
    api_key: Optional[str] = None
    azure_kwargs: Optional[LLMKwargsAzure] = None

class LLMProvider(BaseModel):
    provider: str = Field(..., description="LLM provider name")
    config: LLMConfig

class EmbedderConfig(BaseModel):
    model: str = Field(..., description="Embedder model name")
    azure_kwargs: Optional[LLMKwargsAzure] = None
    
class EmbedderProvider(BaseModel):
    provider: str = Field(..., description="Embedder provider name")
    config: EmbedderConfig = Field(..., description="Configuration for the embedder provider")

class OpenMemoryConfig(BaseModel):    
    custom_instructions: Optional[str] = None
    custom_fact_extraction_prompt: Optional[str] = None
    custom_update_memory_prompt: Optional[str] = None

class VectorStoreConfig(BaseModel):
    provider: str = Field(..., description="Vector store provider name")
    config: Optional[Dict[str, Any]] = Field(
        default_factory=dict, 
        description="Settings used to configure the vector store"
    )

class GraphStoreConfig(BaseModel):
    provider: str = Field(..., description="Graph store provider name")
    config: Optional[Dict[str, Any]] = Field(
        default_factory=dict, 
        description="Settings used to configure the graph store"
    )

class Mem0Config(BaseModel):
    llm: Optional[LLMProvider] = None
    embedder: Optional[EmbedderProvider] = None
    vector_store: Optional[VectorStoreConfig] = None
    graph_store: Optional[GraphStoreConfig] = None
    graph_skip_db: Optional[bool] = None
    enable_graph: Optional[bool] = None
    version: Optional[str] = None

class ConfigSchema(BaseModel):
    openmemory: Optional[OpenMemoryConfig] = None
    mem0: Optional[Mem0Config] = None

def save_config_to_db(db: Session, config: Dict[str, Any] | ConfigSchema, key: str = "main"):
    """Save configuration to database."""

    validated = ConfigSchema.model_validate(config)
    if not validated:
        raise HTTPException(status_code=400, detail="Invalid or missing configuration detected")
    serializable = dict(validated.model_dump(exclude_none=True, exclude_unset=True))
        
    db_config = db.query(ConfigModel).filter(ConfigModel.key == key).first()    
    if db_config:
        db_config.value = serializable # type: ignore - Technically invalid, but will trigger the onupdate to set current time        
        db_config.updated_at = None  # type: ignore - Technically invalid, but will trigger the onupdate to set current time        
    else:
        db_config = ConfigModel(key=key, value=serializable)
        db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config.value

def _reset_config_db(db: Session, key: str = "main"):
    """Deletes the existing configuration record, resetting system to defaults."""

    db_config = db.query(ConfigModel).filter(ConfigModel.key == key).first()
    if db_config:
        db.delete(db_config)
        db.commit()

    # Save the default configuration to database    
    reset_memory_client()

def get_default_config(): 
    """Gets default configuration formatted for the API and database."""
    from app.utils.client_config_factory import get_default_memory_config
    source = get_default_memory_config(expandSecrets=False)
    split = split_config(source)    
    return {
        "openmemory": OpenMemoryConfig.model_validate(split.get("openmemory", {})),
        "mem0": Mem0Config.model_validate(split.get("mem0", {}))
    }

def get_saved_memory_config(expand_secrets: bool = False):
    """Gets saved configuration formatted for the API and database."""
    from app.utils.client_config_factory import get_parsed_memory_config
    source = get_parsed_memory_config(expandSecrets=expand_secrets)
    split = split_config(source)    
    try:        
        parsed = ConfigSchema.model_validate(split)
        return parsed
    except Exception as e:
        logger.error(f"Error validating configuration: {e}")
        raise HTTPException(status_code=500, detail="Invalid configuration format")    


def _is_truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _has_mcp_tool_write_access(current_user: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(current_user, dict):
        return False

    # Accept both RFC scope string and list-shaped claim variants.
    scope_claim = current_user.get("scope") or current_user.get("scp") or ""
    scopes: set[str] = set()
    if isinstance(scope_claim, str):
        scopes = set(scope_claim.split())
    elif isinstance(scope_claim, list):
        scopes = {str(scope).strip() for scope in scope_claim}
    if "mcp_tool:write" in scopes:
        return True

    # Check Keycloak-like nested resource access claims.
    resource_access = current_user.get("resource_access", {})
    if isinstance(resource_access, dict):
        for resource_data in resource_access.values():
            if not isinstance(resource_data, dict):
                continue
            roles = resource_data.get("roles", [])
            permissions = resource_data.get("permissions", [])
            if isinstance(roles, list) and "mcp_tool:write" in roles:
                return True
            if isinstance(permissions, list) and "mcp_tool:write" in permissions:
                return True
    return False


def _log_secrets_access_denial(current_user: Optional[Dict[str, Any]]) -> None:
    auth_present = isinstance(current_user, dict)
    logger.warning(
        "Denied resolved config request without mcp_tool:write access",
        extra={
            "auth_present": auth_present,
            "secrets_requested": True,
            "required_access": "mcp_tool:write",
        },
    )

    span = trace.get_current_span()
    if span is not None:
        span.set_attribute("mem0.config.secrets_requested", True)
        span.set_attribute("mem0.config.secrets_authorized", False)
        span.set_attribute("mem0.config.auth_present", auth_present)
        span.add_event(
            "config.secrets_access_denied",
            {
                "mem0.required_access": "mcp_tool:write",
                "mem0.auth_present": auth_present,
            },
        )

@router.get("/", response_model=ConfigSchema)
@traced_endpoint("config.get")
async def get_configuration(
    secrets: Optional[str] = Query(default=None, include_in_schema=False),
    db: Session = Depends(get_db),
    current_user: Optional[Dict[str, Any]] = Depends(optional_auth),
):
    """Get the current configuration."""
    secrets_requested = _is_truthy(secrets)
    expand_secrets = secrets_requested and _has_mcp_tool_write_access(current_user)
    if secrets_requested and not expand_secrets:
        _log_secrets_access_denial(current_user)
    config = get_saved_memory_config(expand_secrets=expand_secrets)
    if not config:
        # If no configuration exists, return the default configuration
        config = get_default_config()  
    else:
        config = config.model_dump(exclude_none=True, exclude_unset=True)
    return config

@router.put("/", response_model=ConfigSchema)
@traced_endpoint("config.update")
async def update_configuration(config: ConfigSchema, db: Session = Depends(get_db), user = Depends(get_user_record)):
    # require admin or owner-level access to update configuration
    require_admin()
    """Update the configuration."""
    current_config = get_saved_memory_config()
    
    updated_config = current_config.model_copy(deep=True)
        
    # Update openmemory settings if provided
    if config.openmemory is not None:
        if updated_config.openmemory is None:
            updated_config.openmemory = OpenMemoryConfig.model_construct()
        # Convert both to dictionaries and merge        
        merged_dict = {**updated_config.openmemory.model_dump(exclude_none=True, exclude_unset=True), **config.openmemory.model_dump(exclude_none=True, exclude_unset=True)}
        updated_config.openmemory = OpenMemoryConfig.model_validate(merged_dict)
    
    # Update mem0 settings
    if config.mem0 is not None:
        updated_config.mem0 = Mem0Config.model_validate(config.mem0.model_dump(exclude_none=True, exclude_unset=True))
    
    # Save the configuration to database
    save_config_to_db(db, updated_config)
    reset_memory_client()
    return updated_config

@router.post("/reset", response_model=ConfigSchema)
@traced_endpoint("config.reset")
async def reset_configuration(db: Session = Depends(get_db), user = Depends(get_user_record)):
    require_admin()
    """Reset the configuration to default values."""
    try:
        # Get the default configuration with proper provider setups
        _reset_config_db(db)
        reset_memory_client()
        config = get_saved_memory_config()
        return config.model_dump(exclude_none=True, exclude_unset=True)
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to reset configuration: {str(e)}"
        )

@router.get("/mem0/llm", response_model=LLMProvider)
async def get_llm_configuration(db: Session = Depends(get_db)):
    """Get only the LLM configuration."""
    config = get_saved_memory_config()    
    llm_config = config.mem0.llm if config.mem0 else {}    
    return llm_config

@router.put("/mem0/llm", response_model=LLMProvider)
@traced_endpoint("config.update_llm")
async def update_llm_configuration(llm_config: LLMProvider, db: Session = Depends(get_db), user = Depends(get_user_record)):
    require_admin()
    """Update only the LLM configuration."""
    current_config = get_saved_memory_config()
    
    # Ensure mem0 key exists
    if current_config.mem0 is None:
        current_config.mem0 = Mem0Config.model_construct()
    
    # Update the LLM configuration
    current_config.mem0.llm = LLMProvider.model_validate(llm_config)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config.mem0.llm

@router.get("/mem0/embedder", response_model=EmbedderProvider)
async def get_embedder_configuration(db: Session = Depends(get_db)):
    """Get only the Embedder configuration."""
    config = get_saved_memory_config()
    embedder_config = config.mem0.embedder if config.mem0 else {}    
    return embedder_config    

@router.put("/mem0/embedder", response_model=EmbedderProvider)
@traced_endpoint("config.update_embedder")
async def update_embedder_configuration(embedder_config: EmbedderProvider, db: Session = Depends(get_db), user = Depends(get_user_record)):
    require_admin()
    """Update only the Embedder configuration."""
    current_config = get_saved_memory_config()
    
    # Ensure mem0 key exists
    if current_config.mem0 is None:
        current_config.mem0 = Mem0Config.model_construct()
    
    # Update the LLM configuration
    current_config.mem0.embedder = EmbedderProvider.model_validate(embedder_config)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config.mem0.embedder

@router.get("/openmemory", response_model=OpenMemoryConfig)
async def get_openmemory_configuration(db: Session = Depends(get_db)):
    """Get only the OpenMemory configuration."""
    config = get_saved_memory_config()
    openmemory_config = config.openmemory if config.openmemory else OpenMemoryConfig.model_construct()
    return openmemory_config

@router.put("/openmemory", response_model=OpenMemoryConfig)
@traced_endpoint("config.update_openmemory")
async def update_openmemory_configuration(openmemory_config: OpenMemoryConfig, db: Session = Depends(get_db), user = Depends(get_user_record)):
    require_admin()
    """Update only the OpenMemory configuration."""
    current_config = get_saved_memory_config()        
    if current_config.openmemory is None:        
        current_config.openmemory = OpenMemoryConfig.model_construct()
    # Convert both to dictionaries and merge        
    merged_dict = {**current_config.openmemory.model_dump(exclude_none=True, exclude_unset=True), **openmemory_config.model_dump(exclude_none=True, exclude_unset=True)}
    current_config.openmemory = OpenMemoryConfig.model_validate(merged_dict)    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config.openmemory