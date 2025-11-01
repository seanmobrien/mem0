"""Well-known OAuth Protected Resource metadata endpoint.

Implements a small MVC-style controller that returns an RFC 8414 compatible
JSON document for the resource server. We surface key endpoints that resource
servers and clients can use (introspection, revocation, jwks, issuer, token).

This endpoint is intentionally small and derives values from the Keycloak
OpenID configuration (when available) while providing sensible defaults.

Reference: RFC 8414 (OAuth 2.0 Authorization Server Metadata)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Dict, Any
import logging

from app.auth import get_keycloak_openid, KEYCLOAK_SERVER_URL, KEYCLOAK_REALM

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/.well-known/oauth-protected-resource/{resource_path:path}", tags=["well-known"], include_in_schema=True)
@router.get("/.well-known/oauth-protected-resource", tags=["well-known"], include_in_schema=True)
async def oauth_protected_resource_metadata(resource_path: str = "") -> JSONResponse:
	"""Return RFC 8414-like metadata for the protected resource.

	The returned JSON includes common fields resource servers expect such as
	issuer, token and introspection endpoints and the JWKS URI. When Keycloak
	is configured we read its well-known OpenID configuration and derive
	the additional endpoints by convention.
	"""
	try:
		openid = get_keycloak_openid().well_known()
	except Exception as exc:
		logger.debug("Could not load Keycloak well-known configuration: %s", exc)
		openid = {}

	issuer = openid.get("issuer") or f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}"
	token_endpoint = openid.get("token_endpoint") or f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
	authorization_endpoint = openid.get("authorization_endpoint") or f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
	jwks_uri = openid.get("jwks_uri") or f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"

	# Common OAuth endpoints for resource servers (Introspection & Revocation)
	introspection_endpoint = f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token/introspect"
	revocation_endpoint = f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/revoke"

	metadata: Dict[str, Any] = {
		# RFC 8414 core fields
		"issuer": issuer,
		"authorization_endpoint": authorization_endpoint,
		"token_endpoint": token_endpoint,
		"jwks_uri": jwks_uri,

		# Introspection & revocation (RFC 7662 and common extensions)
		"introspection_endpoint": introspection_endpoint,
		"introspection_endpoint_auth_methods_supported": [
			"client_secret_basic",
			"client_secret_post",
			"private_key_jwt",
		],
		"revocation_endpoint": revocation_endpoint,
		"revocation_endpoint_auth_methods_supported": [
			"client_secret_basic",
			"client_secret_post",
			"private_key_jwt",
		],

		# Helpful discovery items for clients/resource servers
		"scopes_supported": ["openid", "profile", "email", "offline_access", "mcp_tool", "mcp_tool:read"],
		"response_types_supported": ["code", "token", "id_token"],
		"grant_types_supported": ["authorization_code", "refresh_token", "client_credentials", "urn:ietf:params:oauth:grant-type:jwt-bearer"],
	}

	# Merge any well-known values we trust from Keycloak (do not overwrite our keys above)
	for k in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
		if openid.get(k) and not metadata.get(k):
			metadata[k] = openid.get(k)

	# Normalize requested resource path (leading slash) and include for callers
	requested_resource = f  "/{resource_path}" if resource_path else ""
	metadata["resource"] = requested_resource

	return JSONResponse(status_code=200, content=metadata)
