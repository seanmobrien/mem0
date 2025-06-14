"""Factory for parasing memory client configurations used to instantiate client configuration objects."""

import os
import json
import hashlib
import socket
import platform

from app.database import SessionLocal

def get_default_memory_config():
    """Get default memory client configuration with sensible defaults."""
    return {
        "llm": {
        "provider": "azure_openai",
        "config": {
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "max_tokens": 2000,
                "api_key": "env:OPENAI_API_KEY",
                "azure_kwargs": {
                    "azure_deployment": "gpt-4o-mini",
                    "api_version": "2025-04-01-preview",
                    "azure_endpoint": "https://schoollaw-1000-eastus096943908820.openai.azure.com/"
                }
            }
        },
        "embedder": {
            "provider": "azure_openai",
            "config": {
                "model": "text-embedding-3-small",
                "azure_kwargs": {
                    "api_key": "env:EMBEDDING_AZURE_OPENAI_API_KEY",
                    "azure_deployment": "text-embedding-3-small",
                    "azure_endpoint": "https://schoollawbot1000.openai.azure.com/",
                    "api_version": "2025-04-01-preview"
            }
        }
        },        
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": "env:PGVECTOR_HOST",
                "port": 8432,
                "dbname": "env:PGVECTOR_DB",
                "user": "env:PGVECTOR_USER",
                "password": "env:PGVECTOR_PASSWORD",
                "collection_name": "env:PGVECTOR_COLLECTION_NAME",
                "embedding_model_dims": 1536,
                "hnsw": True,
                "diskann": False
            }
        },
        "graph_store": {
            "provider": "neo4j",
            "config": {
                "url": "env:NEO4J_URI",
                "username": "NEO4J_USERNAME",
                "password": "env:NEO4J_PASSWORD",
            },
        },
        "version": "v1.1"
    }


def _parse_environment_variables(config_dict):
    """
    Parse environment variables in config values.
    Converts 'env:VARIABLE_NAME' to actual environment variable values.
    """
    if isinstance(config_dict, dict):
        parsed_config = {}
        for key, value in config_dict.items():
            if isinstance(value, str) and value.startswith("env:"):
                env_var = value.split(":", 1)[1]
                env_value = os.environ.get(env_var)
                if env_value:
                    parsed_config[key] = env_value
                    print(f"Loaded {env_var} from environment for {key}")
                else:
                    print(f"Warning: Environment variable {env_var} not found, keeping original value")
                    parsed_config[key] = value
            elif isinstance(value, dict):
                parsed_config[key] = _parse_environment_variables(value)
            else:
                parsed_config[key] = value
        return parsed_config
    return config_dict


def get_parsed_memory_config(custom_instructions: str | None = None): 
    "Retrieves and parses memory client configuration from the database, or"
    "sensable deafults if not available."
    
    try:
        # Start with default configuration
        config = get_default_memory_config()
        
        # Variable to track custom instructions
        db_custom_instructions = None
        db = None
        # Load configuration from database

        # Use custom_instructions parameter first, then fall back to database value
        instructions_to_use = custom_instructions or db_custom_instructions
        if instructions_to_use is not None:
            config["custom_fact_extraction_prompt"] = instructions_to_use

        # ALWAYS parse environment variables in the final config
        # This ensures that even default config values like "env:OPENAI_API_KEY" get parsed
        print("Parsing environment variables in final config...")
        config = _parse_environment_variables(config)
    except Exception as e:
        print(f"Warning: Error loading configuration from database: {e}")
        print("Using default configuration")
        # Continue with default configuration