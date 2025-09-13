# Keycloak Authentication Provider for OpenMemory

This directory contains the Keycloak authentication provider setup for the OpenMemory application.

## Overview

Keycloak serves as the Identity and Access Management (IAM) solution for OpenMemory, providing:
- User authentication and authorization
- OAuth 2.0 / OpenID Connect support
- JWT token generation and validation
- Admin console for user and client management

## Configuration

### Environment Variables

The following environment variables can be configured:

#### Database Configuration
- `KC_DB_URL_HOST`: PostgreSQL database host (default: `postgres`)
- `KC_DB_URL_DATABASE`: Database name (default: `keycloak`)
- `KC_DB_USERNAME`: Database username (default: `keycloak`)
- `KC_DB_PASSWORD`: Database password (default: `keycloak`)

#### Keycloak Server Configuration
- `KC_HOSTNAME`: Keycloak server hostname (default: `localhost`)
- `KC_HTTP_ENABLED`: Enable HTTP (default: `true`)
- `KC_HTTP_PORT`: HTTP port (default: `8080`)
- `KC_HTTPS_PORT`: HTTPS port (default: `8443`)
- `KC_LOG_LEVEL`: Log level (default: `INFO`)

#### Admin User (Initial Setup)
- `KEYCLOAK_ADMIN`: Admin username
- `KEYCLOAK_ADMIN_PASSWORD`: Admin password

### Docker Secrets Support

For production deployments, sensitive values can be provided using Docker secrets:
- `KC_DB_PASSWORD_FILE`: Path to file containing database password
- `KEYCLOAK_ADMIN_PASSWORD_FILE`: Path to file containing admin password

## Building and Running

### Build the Image

```bash
docker build -t openmemory-keycloak .
```

### Run with Docker Compose

The Keycloak service is integrated into the main `docker-compose.yml` file in the parent directory.

### Run Standalone

```bash
docker run -d \
  --name keycloak \
  -p 8080:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin123 \
  -e KC_DB_URL_HOST=your-postgres-host \
  -e KC_DB_USERNAME=keycloak \
  -e KC_DB_PASSWORD=your-password \
  openmemory-keycloak start
```

## Initial Setup

1. **Start the Services**: Ensure PostgreSQL database is running and accessible
2. **Access Admin Console**: Navigate to `http://localhost:8080/admin`
3. **Login**: Use the admin credentials configured via environment variables
4. **Create Realm**: Create a new realm for OpenMemory (recommended: `openmemory`)
5. **Configure Clients**: 
   - Create client for OpenMemory API (confidential client)
   - Create client for OpenMemory UI (public client)

## Client Configuration

### API Client Configuration
- Client ID: `openmemory-api`
- Client Protocol: `openid-connect`
- Access Type: `confidential`
- Valid Redirect URIs: `http://localhost:8765/*`
- Web Origins: `http://localhost:8765`

### UI Client Configuration
- Client ID: `openmemory-ui`
- Client Protocol: `openid-connect`
- Access Type: `public`
- Valid Redirect URIs: `http://localhost:3000/*`
- Web Origins: `http://localhost:3000`

## Security Considerations

1. **Production Deployment**:
   - Always use HTTPS in production
   - Use strong, randomly generated passwords
   - Configure proper network security groups
   - Use Docker secrets for sensitive configuration

2. **Database Security**:
   - Use dedicated PostgreSQL instance
   - Enable SSL/TLS for database connections
   - Regular database backups

3. **Access Control**:
   - Regularly review user access and permissions
   - Implement proper RBAC (Role-Based Access Control)
   - Monitor authentication logs

## Troubleshooting

### Common Issues

1. **Database Connection Failed**:
   - Verify PostgreSQL is running and accessible
   - Check database credentials and network connectivity
   - Ensure database exists and user has proper permissions

2. **Health Check Failures**:
   - Check container logs: `docker logs <container-name>`
   - Verify Keycloak is fully started before health checks
   - Ensure required ports are accessible

3. **Admin Console Access**:
   - Verify admin credentials are correctly set
   - Check if HTTP is enabled for development
   - Ensure proper hostname configuration

### Logs

View container logs:
```bash
docker logs <keycloak-container-name>
```

### Health Checks

Check service health:
```bash
curl http://localhost:8080/health/ready
curl http://localhost:8080/health/live
```