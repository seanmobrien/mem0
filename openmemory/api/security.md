# OpenMemory API Security Documentation

## Overview

The OpenMemory API implements authentication and authorization using Keycloak as the identity provider. This document outlines the security approach, configuration requirements, and implementation details.

## Authentication Architecture

### Identity Provider
- **Keycloak**: Centralized identity and access management
- **Protocol**: OAuth 2.0 / OpenID Connect (OIDC)
- **Token Type**: JWT (JSON Web Tokens)

### Flow
1. Users authenticate with Keycloak
2. Keycloak issues JWT access tokens
3. API validates tokens for each request
4. User information is extracted from validated tokens

## Configuration

The following environment variables must be configured for authentication:

### Keycloak Configuration
- `KEYCLOAK_SERVER_URL`: Keycloak server URL (e.g., `http://keycloak:8080`)
- `KEYCLOAK_REALM`: Keycloak realm name (default: `openmemory`)
- `KEYCLOAK_CLIENT_ID`: API client ID (default: `openmemory-api`)
- `KEYCLOAK_CLIENT_SECRET`: API client secret (for confidential clients)

### Example Configuration
```bash
# Development
KEYCLOAK_SERVER_URL=http://localhost:8080
KEYCLOAK_REALM=openmemory
KEYCLOAK_CLIENT_ID=openmemory-api
KEYCLOAK_CLIENT_SECRET=your-client-secret

# Production
KEYCLOAK_SERVER_URL=https://auth.yourdomain.com
KEYCLOAK_REALM=openmemory
KEYCLOAK_CLIENT_ID=openmemory-api
KEYCLOAK_CLIENT_SECRET=your-production-secret
```

## Protected Endpoints

### Authentication Required
All API endpoints require authentication except:
- `/api/v1/stats/health-check` - Health check endpoint
- `/docs` - API documentation (optional)
- `/openapi.json` - OpenAPI specification (optional)

### Endpoint Protection
Protected endpoints require:
- Valid JWT token in `Authorization` header
- Format: `Bearer <token>`
- Token must be issued by configured Keycloak realm
- Token must not be expired

### Token Validation
The API validates tokens by:
1. Introspecting tokens with Keycloak
2. Verifying token signature and claims
3. Checking token expiration
4. Extracting user information

## User Context

### User Identification
- User ID is extracted from the `sub` claim or `preferred_username`
- This ID is used for all user-scoped operations
- No additional user parameters needed in requests

### Authorization
Currently implements authentication only. Future versions may include:
- Role-based access control (RBAC)
- Resource-level permissions
- Organization/project scoping

## Implementation Details

### Authentication Module
Location: `app/auth.py`

Key functions:
- `get_current_user()`: Validates token and returns user info
- `get_user_id()`: Extracts user ID from token
- `verify_token()`: Validates JWT with Keycloak
- `check_auth_service_health()`: Checks Keycloak connectivity

### Dependencies
```python
from app.auth import get_current_user, get_user_id

# Require authentication
@router.get("/protected")
async def protected_endpoint(
    user_id: str = Depends(get_user_id)
):
    # User is authenticated, user_id contains the authenticated user's ID
    pass
```

### Error Responses
Authentication failures return:
- `401 Unauthorized`: Invalid or expired token
- `403 Forbidden`: Insufficient permissions (future use)
- `503 Service Unavailable`: Keycloak unavailable

## Security Best Practices

### Token Handling
- Tokens should be stored securely on the client side
- Use HTTPS in production to protect tokens in transit
- Implement proper token refresh mechanisms
- Set appropriate token expiration times

### Client Configuration
- Use confidential clients for server-side applications
- Use public clients for SPAs/mobile apps
- Configure proper redirect URIs
- Implement PKCE for public clients

### Network Security
- Use HTTPS for all communication
- Configure CORS appropriately
- Use reverse proxies for additional security
- Implement rate limiting

### Monitoring and Logging
- Log authentication failures
- Monitor token usage patterns
- Set up alerts for unusual activity
- Audit user access regularly

## Troubleshooting

### Common Issues

1. **Token Validation Failed**
   - Check Keycloak connectivity
   - Verify realm and client configuration
   - Ensure token is not expired

2. **Service Unavailable**
   - Check Keycloak server status
   - Verify network connectivity
   - Check configuration variables

3. **User Not Found**
   - Verify user exists in Keycloak
   - Check user ID mapping
   - Ensure proper token claims

### Debugging
- Check health endpoint: `/api/v1/stats/health-check`
- Review application logs for authentication errors
- Use Keycloak admin console to verify configuration
- Test token validation manually

### Health Check
The health check endpoint includes authentication service status:
```json
{
  "details": {
    "auth_service": {
      "healthy": true,
      "server_url": "http://keycloak:8080",
      "realm": "openmemory",
      "client_id": "openmemory-api"
    }
  }
}
```

## Development Setup

1. **Start Keycloak**: `docker-compose up keycloak`
2. **Configure Realm**: Create `openmemory` realm
3. **Create Client**: Configure `openmemory-api` client
4. **Set Environment Variables**: Update `.env` file
5. **Test Authentication**: Use valid JWT tokens

## Production Deployment

1. **Use HTTPS**: Configure SSL certificates
2. **Secure Secrets**: Use proper secret management
3. **Database Security**: Secure Keycloak database
4. **Network Isolation**: Use proper network segmentation
5. **Monitoring**: Implement security monitoring
6. **Backup**: Regular configuration and data backups