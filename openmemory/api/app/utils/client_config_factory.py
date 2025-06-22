"""
Factory for parsing memory client configurations used to instantiate client configuration objects.

Docker Ollama Configuration:
When running inside a Docker container and using Ollama as the LLM or embedder provider,
the system automatically detects the Docker environment and adjusts localhost URLs
to properly reach the host machine where Ollama is running.

Supported Docker host resolution (in order of preference):
1. OLLAMA_HOST environment variable (if set)
2. host.docker.internal (Docker Desktop for Mac/Windows)
3. Docker bridge gateway IP (typically 172.17.0.1 on Linux)
4. Fallback to 172.17.0.1

Example configuration that will be automatically adjusted:
{
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3.1:latest",
            "ollama_base_url": "http://localhost:11434"  # Auto-adjusted in Docker
        }
    }
}
"""

import json
import os
from typing import Any
import datetime
import logging
import socket
from app.database import SessionLocal, Base
from sqlalchemy import text

def get_current_utc_time():
    """Get current UTC time"""
    return datetime.datetime.now(datetime.UTC)

logger = logging.getLogger(__name__)

def parse_environment_variable_value(name, defaultValue: Any = None, expandSecrets: bool = True): 
    """
    Parse a single environment variable value.
    Handles 'env:VARIABLE_NAME' format and returns the actual value.
    """
    if not expandSecrets:
        # If we are not expanding secrets, just return the name as-is
        return name
    # Check if the name starts with 'env:'
    if isinstance(name, str) and name.startswith("env:"):
        parts = name.split(":", 1)
        # It does - look for type-specific handling
        if parts[1].startswith("int:"):
            # Handle 'env:int:VARIABLE_NAME' format for integers
            parts = parts[1].split(":", 1)            
            raw_value = os.environ.get(parts[1], defaultValue)
            if raw_value is not None:
                try:
                    return int(raw_value)
                except ValueError:
                    logger.warning(f"Warning: Environment variable {parts[1]} is not a valid integer")
                    return defaultValue
        
        if parts[1].startswith("bool:"):
            # Handle 'env:bool:VARIABLE_NAME' format for booleans
            parts = parts[1].split(":", 1)
            raw_value = os.environ.get(parts[1], defaultValue)
            if raw_value is not None:
                if isinstance(raw_value, bool):
                    return raw_value
                if str(raw_value).lower() in ['true', '1', 'yes']:
                    return True
                if str(raw_value).lower() in ['false', '0', 'no']:
                    return False
                logger.warning(f"Warning: Environment variable {parts[1]} is not a valid boolean")                    
                return defaultValue
            
        if parts[1].startswith("float:"):
            # Handle 'env:float:VARIABLE_NAME' format for floats
            parts = parts[1].split(":", 1)
            raw_value = os.environ.get(parts[1], defaultValue)
            if raw_value is not None:
                try:
                    return float(raw_value)
                except ValueError:
                    logger.warning(f"Warning: Environment variable {parts[2]} is not a valid float")
                    return defaultValue

        # Handle 'env:VARIABLE_NAME' format for strings
        raw_value = os.environ.get(parts[1], defaultValue)
        if raw_value is not None:
            return raw_value  
        logger.debug(f"Warning: Environment variable {parts[1]} not found, using a default value.")
        return defaultValue
    
    # Otherwise, this is not an environment variable, return it as-is
    return name            
            
def parse_environment_variables(config_dict, expandSecrets: bool = True):
    """
    Parse environment variables in config values.
    Converts 'env:VARIABLE_NAME' to actual environment variable values.
    """
    if isinstance(config_dict, dict):
        parsed_config = {}
        for key, value in config_dict.items():
            # Make a working copy of value so that we aren't modifying our iteratro           
            workingValue = value
            if isinstance(workingValue, str):
                workingValue = parse_environment_variable_value(workingValue, expandSecrets)                
            elif isinstance(workingValue, dict):
                # Recursively parse nested dictionaries
                parsed_config[key] = parse_environment_variables(value, expandSecrets)
                continue
            # Make sure we don't have a null
            if workingValue is None:
                # If the value is None, we do not copy it over
                logger.debug(f"Warning: Environment variable for {key} is None, no defaultvalue available")
                continue
            # If we made it this far, we can safely assign the value
            parsed_config[key] = workingValue
        return parsed_config
    return parse_environment_variable_value(config_dict, expandSecrets)

def _get_docker_host_url():
    """
    Determine the appropriate host URL to reach host machine from inside Docker container.
    Returns the best available option for reaching the host from inside a container.
    """
    # Check for custom environment variable first
    custom_host = os.environ.get('OLLAMA_HOST')
    if custom_host:
        print(f"Using custom Ollama host from OLLAMA_HOST: {custom_host}")
        return custom_host.replace('http://', '').replace('https://', '').split(':')[0]
    
    # Check if we're running inside Docker
    if not os.path.exists('/.dockerenv'):
        # Not in Docker, return localhost as-is
        return "localhost"
    
    print("Detected Docker environment, adjusting host URL for Ollama...")
    
    # Try different host resolution strategies
    host_candidates = []
    
    # 1. host.docker.internal (works on Docker Desktop for Mac/Windows)
    try:
        socket.gethostbyname('host.docker.internal')
        host_candidates.append('host.docker.internal')
        print("Found host.docker.internal")
    except socket.gaierror:
        pass
    
    # 2. Docker bridge gateway (typically 172.17.0.1 on Linux)
    try:
        with open('/proc/net/route', 'r') as f:
            for line in f:
                fields = line.strip().split()
                if fields[1] == '00000000':  # Default route
                    gateway_hex = fields[2]
                    gateway_ip = socket.inet_ntoa(bytes.fromhex(gateway_hex)[::-1])
                    host_candidates.append(gateway_ip)
                    print(f"Found Docker gateway: {gateway_ip}")
                    break
    except (FileNotFoundError, IndexError, ValueError):
        pass
    
    # 3. Fallback to common Docker bridge IP
    if not host_candidates:
        host_candidates.append('172.17.0.1')
        print("Using fallback Docker bridge IP: 172.17.0.1")
    
    # Return the first available candidate
    return host_candidates[0]

def fix_ollama_urls(config_section):
    """
    Fix Ollama URLs for Docker environment.
    Replaces localhost URLs with appropriate Docker host URLs.
    Sets default ollama_base_url if not provided.
    """
    if not config_section or "config" not in config_section:
        return config_section
    
    ollama_config = config_section["config"]
    
    # Set default ollama_base_url if not provided
    if "ollama_base_url" not in ollama_config:
        ollama_config["ollama_base_url"] = "http://host.docker.internal:11434"
    else:
        # Check for ollama_base_url and fix if it's localhost
        url = ollama_config["ollama_base_url"]
        if "localhost" in url or "127.0.0.1" in url:
            docker_host = _get_docker_host_url()
            if docker_host != "localhost":
                new_url = url.replace("localhost", docker_host).replace("127.0.0.1", docker_host)
                ollama_config["ollama_base_url"] = new_url
                print(f"Adjusted Ollama URL from {url} to {new_url}")
    
    return config_section

def get_default_memory_config(expandSecrets: bool = True) -> dict:
    """Get default memory client configuration with sensible defaults that can be overriden by environment variables."""

    withModel = parse_environment_variable_value("env:LLM_AZURE_DEPLOYMENT", "gpt-4o-mini", expandSecrets = expandSecrets)
    withEmbeddingModel = parse_environment_variable_value("env:EMBEDDING_AZURE_DEPLOYMENT", "text-embedding-3-small", expandSecrets = expandSecrets)

    llmProvider = parse_environment_variable_value("env:MEM0_PROVIDER_LLM", "openai")
    embedderProvider = parse_environment_variable_value("env:MEM0_PROVIDER_EMBEDDER", llmProvider)
    vectorProvider = parse_environment_variable_value("env:MEM0_PROVIDER_VECTORSTORE")
    graphProvider = parse_environment_variable_value("env:MEM0_PROVIDER_GRAPHSTORE")
    customExtractionPrompt = parse_environment_variable_value("env:MEM0_EXTRACTION_PROMPT", None, expandSecrets)

    defaultValues: dict = {
        "llm": {
            "provider": llmProvider,
            "config": {
                "model": withModel,
                "temperature": parse_environment_variable_value("env:float:MODEL_TEMP", .1, expandSecrets),
                "max_tokens": parse_environment_variable_value("env:int:MODEL_MAX_TOKENS", 2000, expandSecrets),
                "api_key": parse_environment_variable_value("env:OPENAI_API_KEY", expandSecrets = expandSecrets),
            }
        },
        "embedder": {
            "provider": embedderProvider,
            "config": {
                "model": withEmbeddingModel,
            }
        },
        "version": "v1.1"
    }
    temp = defaultValues["llm"]["config"]["temperature"]
    if isinstance(temp, float) and temp <= 0:    
        # Tricky, because 0 can be an actual intentional value.  Log and leave it be
        logger.warning("Warning: LLM temperature is set to 0, which may not be ideal for most use cases. Ensure this is on purpose and not a misset value (default is .1).")
    temp = defaultValues["llm"]["config"]["max_tokens"]
    if isinstance(temp, int) and temp <= 0:
        # Much easier - we should naver have a max of 0 tokens
        logger.warning("Warning: LLM max_tokens is set to 0 or less, which will cause errors. Defaulting to 2000 tokens.")
        defaultValues["llm"]["config"]["max_tokens"] = 2000

    # Setup azure-specific defaults
    if llmProvider == "azure_openai":
        withApiVersion = parse_environment_variable_value("env:LLM_AZURE_API_VERSION", "2025-04-01-preview", expandSecrets = expandSecrets)

        defaultValues["llm"]["config"]["azure_kwargs"] = {
            "azure_deployment": withModel,
            "api_version": withApiVersion,
            "azure_endpoint": parse_environment_variable_value("env:LLM_AZURE_ENDPOINT", "https://schoollaw-1000-eastus096943908820.openai.azure.com/", expandSecrets = expandSecrets)
        }
        defaultValues["embedder"]["config"]["azure_kwargs"] = {
            "api_key": "env:EMBEDDING_AZURE_OPENAI_API_KEY",
            "azure_deployment": withEmbeddingModel,
            "azure_endpoint": parse_environment_variable_value("env:EMBEDDING_AZURE_ENDPOINT","https://schoollawbot1000.openai.azure.com/", expandSecrets = expandSecrets),
            "api_version": withApiVersion
        }
    # Vector Store
    if not vectorProvider is None:
        defaultValues["vector_store"] = {
            "provider": vectorProvider,
            "config": {}
        }
        if vectorProvider == "pgvector":
            defaultValues["vector_store"]["config"] = {
                "host": parse_environment_variable_value("env:PGVECTOR_HOST", "postgres", expandSecrets = expandSecrets),
                "port": parse_environment_variable_value("env:int:PGVECTOR_PORT", 5432, expandSecrets = expandSecrets),
                "dbname": parse_environment_variable_value("env:PGVECTOR_DB", "postgres", expandSecrets = expandSecrets),
                "user": parse_environment_variable_value("env:PGVECTOR_USER", "postgres", expandSecrets = expandSecrets),
                "password": parse_environment_variable_value("env:PGVECTOR_PASSWORD", expandSecrets = expandSecrets),
                "collection_name": parse_environment_variable_value("env:PGVECTOR_COLLECTION_NAME", "memories", expandSecrets = expandSecrets),
                "embedding_model_dims": parse_environment_variable_value("env:int:EMBEDDING_DIMENSIONS", 1536, expandSecrets = expandSecrets),
                "hnsw": parse_environment_variable_value("env:bool:PG_HNSW", False, expandSecrets = expandSecrets),
                "diskann": parse_environment_variable_value("env:bool:PG_TIMESCALE", True, expandSecrets = expandSecrets)
            }
        else:
            logger.debug(f"Warning - defaults have not been set for vector store provider {vectorProvider}, it will need to be manually configured before use.")
            
    # Graph Store
    if not graphProvider is None:
        defaultValues["graph_store"] = {
            "provider": parse_environment_variable_value(graphProvider),
            "config": {
                "url": parse_environment_variable_value("env:GRAPH_URI", expandSecrets = expandSecrets),
                "username": parse_environment_variable_value("env:GRAPH_USERNAME", "neo4j", expandSecrets = expandSecrets),
                "password": parse_environment_variable_value("env:GRAPH_PASSWORD", expandSecrets = expandSecrets),
            }
        }

    # Custom Fact Extraction Prompt
    if customExtractionPrompt is not None:
        defaultValues["custom_fact_extraction_prompt"] = parse_environment_variable_value(customExtractionPrompt, expandSecrets = expandSecrets)

    return defaultValues    

def _get_config_from_database() -> dict | None:    
    """
    Retrieves the `value` column of the record with a key of 'main'
    and returns it as a Python dictionary.  This is done so that we can
    avoid circular imports while still pulling the same configuration as 
    the Memory instance uses.
    """
    db = None
    try:
        db = SessionLocal()
        query = text("SELECT value FROM configs WHERE key = :key LIMIT 1")
        result = db.execute(query, {"key": "main"}).fetchone()
        return json.loads(result[0]) if not result is None and len(result) > 0 else None
    except Exception as e:
        logger.error(f"Error retrieving configuration from database: {e}")
        return None
    finally:
        if db is not None:
            db.close()


def _copy_from_db(target: dict, db: dict, key: str):
    """
    Copies a value from the database dictionary to the target dictionary
    if the key exists in the database.
    """
    if key in db and db[key] is not None:
        if target.get(key) is None:
            # If the target key does not exist, copy it right on over from the database
            target[key] = db[key]
        elif isinstance(target[key], dict) and isinstance(db[key], dict):
            # If both are dictionaries, merge them
            target[key].update(db[key])        
    else:
        logger.debug(f"Warning: Key '{key}' not found in database configuration, using default value."    )

def get_parsed_memory_config(custom_instructions: str | None = None, expandSecrets: bool = True): 
    "Retrieves and parses memory client configuration from the database, or"
    "sensable deafults if not available."    
    config: dict | None = None
    db = None
    try:        
        # Start with default configuration
        config = get_default_memory_config(expandSecrets)
                      
        # Use custom_instructions parameter first, then fall back to database value
        instructions_to_use = custom_instructions
        if instructions_to_use is not None:
            config.update({"custom_fact_extraction_prompt": instructions_to_use})
        
        # Load configuration from database
        json_config = _get_config_from_database()

        if json_config:                    
            # Extract custom instructions from openmemory settings
            if "openmemory" in json_config and "custom_instructions" in json_config["openmemory"] and custom_instructions is None:
                config["custom_fact_extraction_prompt"] = json_config["openmemory"]["custom_instructions"]
            
            # Override defaults with configurations from the database
            if "mem0" in json_config:
                mem0_config = json_config["mem0"]                
                # Update configuration sections where available
                _copy_from_db(config, mem0_config, "llm")
                _copy_from_db(config, mem0_config, "embedder")
                _copy_from_db(config, mem0_config, "vector_store")
                _copy_from_db(config, mem0_config, "graph_store")                
            
            # All done!
            logger.debug("Configuration data has been successfully merged.")
        else:       
            logger.debug("No saved configuration overides found, defaults will be used.")
       
        # Fix Ollama URLs for Docker if needed
        if config["llm"].get("provider") == "ollama":
            config["llm"] = fix_ollama_urls(config["llm"])
        if config["embedder"].get("provider") == "ollama":            
            config["embedder"] = fix_ollama_urls(config["embedder"])            
        
        # If expandSecrets is false then we don't want to mess with environment variables
        # This supports loading and saving configuration source vs. resolved values
        if (expandSecrets):
            parsedConfig: Any = parse_environment_variables(config, expandSecrets)
            if isinstance(parsedConfig, dict):
                config = parsedConfig        
        return config
    except Exception as e:
        logger.warning(f"Warning: Error loading configuration from database: {e}; default configuration will be used.")        
        # Continue with default configuration
        return config if config is not None else get_default_memory_config(expandSecrets=expandSecrets)
    
def split_config(config: dict):
    """
    Splits the configuration into separate sections for openmemory and mem0.
    Returns a dictionary with 'openmemory' and 'mem0' keys.
    """
    ret: dict[str, dict] = {}    
    custom_instructions = config.pop("custom_fact_extraction_prompt", None)

    ret["openmemory"] = dict([["custom_instructions", custom_instructions]])
    ret["mem0"] = dict([["llm", config.get("llm", {})],
                        ["embedder", config.get("embedder", {})],
                        ["vector_store", config.get("vector_store", {})],
                        ["graph_store", config.get("graph_store", {})],
                        ["version", config.get("version", "v1.1")]])
    return ret
