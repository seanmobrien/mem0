import os
import json
from typing import Dict, Any, Optional
from app.utils.clientConfigFactory import split_config
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import logging
from app.database import get_db
from app.models import Config as ConfigModel
from app.utils.memory import reset_memory_client
#from app.utils.clientConfigFactory import get_default_memory_config, get_parsed_memory_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["config"])

class LLMConfig(BaseModel):
    model: str = Field(..., description="LLM model name")
    temperature: Optional[float | str] = Field(..., description="Temperature setting for the model")
    max_tokens: Optional[int| str] = Field(..., description="Maximum tokens to generate")
    api_key: Optional[str] = Field(..., description="API key or 'env:LLM_AZURE_OPENAI_API_KEY' to use environment variable")    
    azure_kwargs: Optional[Dict[str, Any]] = Field(
        default_factory=dict, 
        description="Azure-specific parameters for the embedder, such as api_key, azure_deployment, azure_endpoint, and api_version"
    )

class LLMProvider(BaseModel):
    provider: str = Field(..., description="LLM provider name")
    config: LLMConfig

class EmbedderConfig(BaseModel):
    model: str = Field(..., description="Embedder model name")
    azure_kwargs: Optional[Dict[str, Any]] = Field(
        default_factory=dict, 
        description="Azure-specific parameters for the embedder, such as api_key, azure_deployment, azure_endpoint, and api_version"
    )
    
class EmbedderProvider(BaseModel):
    provider: str = Field(..., description="Embedder provider name")
    config: EmbedderConfig

class OpenMemoryConfig(BaseModel):
    custom_instructions: Optional[str] = Field(..., description="Custom instructions for memory management and fact extraction")

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
    enable_graph: Optional[bool] = Field(..., description="If True, enables the graph store for advanced querying and relationships")
    version: Optional[str] = Field(..., description="Version of the Mem0 configuration, defaults to 'v1'")

class ConfigSchema(BaseModel):
    openmemory: Optional[OpenMemoryConfig] = None
    mem0: Optional[Mem0Config] = None

def save_config_to_db(db: Session, config: Dict[str, Any], key: str = "main"):
    """Save configuration to database."""
    db_config = db.query(ConfigModel).filter(ConfigModel.key == key).first()
    
    if db_config:
        db_config.value = config
        db_config.updated_at = None  # Will trigger the onupdate to set current time
    else:
        db_config = ConfigModel(key=key, value=config)
        db.add(db_config)
        
    db.commit()
    db.refresh(db_config)
    return db_config.value

def get_default_config(): 
    """Gets default configuration formatted for the API and database."""
    from app.utils.clientConfigFactory import get_default_memory_config
    source = get_default_memory_config(expandSecrets=False)
    split = split_config(source)    
    return {
        "openmemory": OpenMemoryConfig(split.get("openmemory", {})),
        "mem0": Mem0Config(split.get("mem0", {}))
    }

def get_saved_memory_config():
    """Gets saved configuration formatted for the API and database."""
    from app.utils.clientConfigFactory import get_parsed_memory_config
    source = get_parsed_memory_config(expandSecrets=False)
    split = split_config(source)
    ret = {}
    try:
        parsed = ConfigSchema.validate_json(json.dumps(source))
        return parsed
    except Exception as e:
        logger.error(f"Error validating configuration: {e}")
        raise HTTPException(status_code=500, detail="Invalid configuration format")
    
    return ret


@router.get("/", response_model=ConfigSchema)
async def get_configuration(db: Session = Depends(get_db)):
    """Get the current configuration."""
    config = get_saved_memory_config()
    return config

@router.put("/", response_model=ConfigSchema)
async def update_configuration(config: ConfigSchema, db: Session = Depends(get_db)):
    """Update the configuration."""
    current_config = get_saved_memory_config()
    
    # Convert to dict for processing
    updated_config = current_config.copy()
    
    # Update openmemory settings if provided
    if config.openmemory is not None:
        if "openmemory" not in updated_config:
            updated_config["openmemory"] = {}
        updated_config["openmemory"].update(OpenMemoryConfig(config.openmemory).dict(exclude_none=True))
    
    # Update mem0 settings
    updated_config["mem0"] = Mem0Config(config.mem0).dict(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, updated_config)
    reset_memory_client()
    return updated_config

@router.post("/reset", response_model=ConfigSchema)
async def reset_configuration(db: Session = Depends(get_db)):
    """Reset the configuration to default values."""
    try:
        # Get the default configuration with proper provider setups
        default_config = get_default_config()
        
        # Save it as the current configuration in the database
        save_config_to_db(db, default_config)
        reset_memory_client()
        return default_config
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to reset configuration: {str(e)}"
        )

@router.get("/mem0/llm", response_model=LLMProvider)
async def get_llm_configuration(db: Session = Depends(get_db)):
    """Get only the LLM configuration."""
    config = get_saved_memory_config()
    llm_config = config.get("mem0", {}).get("llm", {})
    return llm_config

@router.put("/mem0/llm", response_model=LLMProvider)
async def update_llm_configuration(llm_config: LLMProvider, db: Session = Depends(get_db)):
    """Update only the LLM configuration."""
    current_config = get_saved_memory_config()
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the LLM configuration
    current_config["mem0"]["llm"] = llm_config.dict(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["llm"]

@router.get("/mem0/embedder", response_model=EmbedderProvider)
async def get_embedder_configuration(db: Session = Depends(get_db)):
    """Get only the Embedder configuration."""
    config = get_saved_memory_config()
    embedder_config = config.get("mem0", {}).get("embedder", {})
    return embedder_config

@router.put("/mem0/embedder", response_model=EmbedderProvider)
async def update_embedder_configuration(embedder_config: EmbedderProvider, db: Session = Depends(get_db)):
    """Update only the Embedder configuration."""
    current_config = get_saved_memory_config()
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the Embedder configuration
    current_config["mem0"]["embedder"] = embedder_config.dict(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["embedder"]

@router.get("/openmemory", response_model=OpenMemoryConfig)
async def get_openmemory_configuration(db: Session = Depends(get_db)):
    """Get only the OpenMemory configuration."""
    config = get_saved_memory_config()
    openmemory_config = config.get("openmemory", {})
    return openmemory_config

@router.put("/openmemory", response_model=OpenMemoryConfig)
async def update_openmemory_configuration(openmemory_config: OpenMemoryConfig, db: Session = Depends(get_db)):
    """Update only the OpenMemory configuration."""
    current_config = get_saved_memory_config()
    
    # Ensure openmemory key exists
    if "openmemory" not in current_config:
        current_config["openmemory"] = {}
    
    # Update the OpenMemory configuration
    current_config["openmemory"].update(openmemory_config.dict(exclude_none=True))
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["openmemory"] 