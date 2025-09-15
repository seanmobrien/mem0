"""
Authentication and Authorization module for OpenMemory API

This module provides JWT token validation and user authentication
using Keycloak as the identity provider.
"""

import datetime
import os
import logging
from typing import Optional, Dict, Any
from app.database import get_db
from app.models import User
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from keycloak import KeycloakOpenID
import requests
from functools import lru_cache

logger = logging.getLogger(__name__)

# Security scheme for Bearer token
security = HTTPBearer()

# Configuration from environment variables
KEYCLOAK_SERVER_URL = os.getenv("KEYCLOAK_SERVER_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "openmemory")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "openmemory-api")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
ADMIN_ROLE = "memory_admin"

# Feature flag for authentication (can be disabled for development)
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() in ("true", "1", "yes", "on")

# Cache for Keycloak configuration
_keycloak_openid: Optional[KeycloakOpenID] = None
_jwks_cache: Optional[Dict[str, Any]] = None


@lru_cache(maxsize=1)
def get_keycloak_openid() -> KeycloakOpenID:
    """Get Keycloak OpenID instance (cached)"""
    global _keycloak_openid
    if _keycloak_openid is None:
        _keycloak_openid = KeycloakOpenID(
            server_url=KEYCLOAK_SERVER_URL,
            client_id=KEYCLOAK_CLIENT_ID,
            realm_name=KEYCLOAK_REALM,
            client_secret_key=KEYCLOAK_CLIENT_SECRET,
            verify=True
        )
    return _keycloak_openid


def get_jwks() -> Dict[str, Any]:
    """Get JWKS (JSON Web Key Set) from Keycloak"""
    global _jwks_cache
    
    if _jwks_cache is None:
        try:
            keycloak_openid = get_keycloak_openid()
            _jwks_cache = keycloak_openid.certs()
        except Exception as e:
            logger.error(f"Failed to fetch JWKS from Keycloak: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable"
            )
    
    return _jwks_cache


def verify_token(token: str) -> Dict[str, Any]:
    """
    Verify JWT token with Keycloak
    
    Args:
        token: JWT token string
        
    Returns:
        Dict containing token payload
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        keycloak_openid = get_keycloak_openid()
        
        # Verify token with Keycloak
        token_info = keycloak_openid.introspect(token)
        
        if not token_info.get("active", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is not active",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if (not has_role(token_info, "memory_user")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        
        return token_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        Dict containing user information from token
        
    Raises:
        HTTPException: If authentication fails
    """
    if not AUTH_ENABLED:
        # Return a default user for development when auth is disabled
        return {
            "sub": "dev-user",
            "preferred_username": "dev-user",
            "email": "dev@example.com",
            "name": "Development User"
        }
    
    token = credentials.credentials
    return verify_token(token)


def optional_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[Dict[str, Any]]:
    """
    Optional authentication dependency for endpoints that can work with or without auth
    
    Args:
        credentials: Optional HTTP authorization credentials
        
    Returns:
        Dict containing user information if authenticated, None otherwise
    """
    if credentials is None:
        return None
    
    try:
        return verify_token(credentials.credentials)
    except HTTPException:
        return None


def has_role(user: Dict[str, Any], role: str) -> bool:
    """
    Check if user has a specific role
    
    Args:
        user: User information from token
        role: Role name to check
        
    Returns:
        True if user has the role, False otherwise
    """
    resource_access = user.get("resource_access", {})
    client_roles = resource_access.get(KEYCLOAK_CLIENT_ID, {}).get("roles", [])
    realm_roles = user.get("realm_access", {}).get("roles", [])
    
    return role in client_roles or role in realm_roles


def require_role(required_role: str):
    """
    Decorator to require a specific role for endpoint access
    
    Args:
        required_role: Role name required for access
        
    Returns:
        Dependency function that validates role
    """
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if not has_role(current_user, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role}"
            )
        return current_user
    
    return role_checker

def require_admin():
    return require_role(ADMIN_ROLE)

def get_user_id(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """
    Extract user ID from authenticated user
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User ID string
    """
    if not AUTH_ENABLED:
        return current_user.get("preferred_username", "dev-user")
    
    user_id = current_user.get("sub") or current_user.get("preferred_username")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID not found in token"
        )
    return user_id

def get_user_record(current_user: Dict[str, Any] = Depends(get_current_user), db = Depends(get_db)) -> User: # type: ignore
    """
    Retrieve user record from database based on authenticated user ID
    
    Args:
        current_user: Authenticated user information
        db: Database session
        Returns:
            User record from database
    """
    current_user_id = get_user_id(current_user)
    user = db.query(User).filter(User.user_id == current_user_id).first()
    if not user:
        new_user = User(
            name=user.get("firstName", "") + " " + user.get("lastName", ""),
            email=user.get("email", None),
            user_id=user_id,
            metadata_= {},
            created_at=datetime.datetime.now(datetime.UTC),
            updated_at=datetime.datetime.now(datetime.UTC),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)    
    return user

# Health check function for authentication service
def check_auth_service_health() -> Dict[str, Any]:
    """
    Check if Keycloak authentication service is healthy
    
    Returns:
        Dict with health status information
    """
    if not AUTH_ENABLED:
        return {
            "healthy": True,
            "enabled": False,
            "message": "Authentication is disabled"
        }
    
    try:
        # Try to get well-known configuration
        well_known_url = f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/.well-known/openid_configuration"
        response = requests.get(well_known_url, timeout=5)
        response.raise_for_status()
        
        return {
            "healthy": True,
            "enabled": True,
            "server_url": KEYCLOAK_SERVER_URL,
            "realm": KEYCLOAK_REALM,
            "client_id": KEYCLOAK_CLIENT_ID
        }
    except Exception as e:
        return {
            "healthy": False,
            "enabled": True,
            "error": str(e),
            "server_url": KEYCLOAK_SERVER_URL,
            "realm": KEYCLOAK_REALM
        }