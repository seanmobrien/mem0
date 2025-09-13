# OpenMemory UI Security Documentation

## Overview

The OpenMemory UI implements authentication using NextAuth.js with Keycloak as the identity provider. This document outlines the security approach, configuration requirements, and implementation details for the frontend application.

## Authentication Architecture

### Authentication Library
- **NextAuth.js**: Industry-standard authentication library for Next.js
- **Provider**: Keycloak (OpenID Connect)
- **Session Strategy**: JWT (JSON Web Tokens)
- **Middleware**: Route protection and authentication enforcement

### Flow
1. User accesses protected route
2. Middleware checks for valid session
3. If no session, redirect to sign-in page
4. User authenticates with Keycloak
5. Keycloak redirects back with tokens
6. NextAuth.js creates secure session
7. Access token is included in API requests

## Configuration

The following environment variables must be configured:

### NextAuth Configuration
- `NEXTAUTH_URL`: Application URL (e.g., `http://localhost:3000`)
- `NEXTAUTH_SECRET`: Secret key for JWT encryption (must be random and secure)

### Keycloak Configuration  
- `KEYCLOAK_ID`: Keycloak client ID (default: `openmemory-ui`)
- `KEYCLOAK_SECRET`: Keycloak client secret (leave empty for public clients)
- `KEYCLOAK_ISSUER`: Keycloak issuer URL (e.g., `http://localhost:8080/realms/openmemory`)

### Example Configuration
```bash
# Development
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-random-secret-key-32-chars-min
KEYCLOAK_ID=openmemory-ui
KEYCLOAK_SECRET=
KEYCLOAK_ISSUER=http://localhost:8080/realms/openmemory

# Production
NEXTAUTH_URL=https://ui.yourdomain.com
NEXTAUTH_SECRET=your-production-secret-key
KEYCLOAK_ID=openmemory-ui
KEYCLOAK_SECRET=your-client-secret-if-confidential
KEYCLOAK_ISSUER=https://auth.yourdomain.com/realms/openmemory
```

## Protected Routes

### Authentication Required
All routes require authentication except:
- `/auth/signin` - Sign-in page
- `/auth/error` - Authentication error page
- `/api/auth/*` - NextAuth.js API routes

### Route Protection
- **Middleware**: Automatically redirects unauthenticated users to `/auth/signin`
- **Session Check**: Validates session on each route access
- **Token Refresh**: Automatically handled by NextAuth.js

## Implementation Details

### Authentication Configuration
Location: `app/api/auth/[...nextauth]/route.ts`

Key features:
- Keycloak provider configuration
- JWT token handling
- Session customization
- Custom sign-in and error pages

### Middleware Protection
Location: `middleware.ts`

Functions:
- Route-based authentication enforcement
- Automatic redirect to sign-in page
- Prevention of authenticated users accessing auth pages

### Authentication Hook
Location: `hooks/useAuth.ts`

Provides:
- Current user information
- Authentication status
- Loading states
- Token access

### API Client Integration
Location: `lib/api-client.ts`

Features:
- Automatic token injection in API requests
- Token refresh handling
- Automatic redirect on 401 errors

## User Interface Components

### Navigation Bar
- User avatar/profile dropdown
- Sign-out functionality
- User information display

### Authentication Pages
- **Sign-in Page**: `/auth/signin`
  - Provider-based authentication
  - Error handling
  - Responsive design

- **Error Page**: `/auth/error`
  - Error message display
  - Retry functionality
  - Navigation options

## Security Features

### Session Management
- Secure JWT storage
- Automatic token refresh
- Session expiration handling
- Secure cookie configuration

### Route Protection
- Middleware-based protection
- Automatic redirects
- Session validation
- Protected API routes

### Token Handling
- Secure token storage
- Automatic token injection
- Token expiration handling
- Refresh token management

## Security Best Practices

### Environment Variables
- Use strong, random secrets
- Never commit secrets to version control
- Use different secrets for different environments
- Rotate secrets regularly

### HTTPS in Production
- Always use HTTPS in production
- Configure proper SSL certificates
- Use HSTS headers
- Implement proper CORS policies

### Session Security
- Set appropriate session expiration
- Use secure cookie settings
- Implement proper logout functionality
- Clear sessions on security events

## Development Setup

1. **Install Dependencies**:
   ```bash
   npm install next-auth
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your configuration
   ```

3. **Setup Keycloak Client**:
   - Create public client in Keycloak
   - Configure redirect URIs
   - Set valid web origins

4. **Test Authentication**:
   - Start development server
   - Navigate to protected route
   - Verify redirect to sign-in

## Production Deployment

### Security Checklist
- [ ] Use HTTPS for all communication
- [ ] Generate strong NEXTAUTH_SECRET
- [ ] Configure proper CORS settings
- [ ] Set up security headers
- [ ] Configure CSP (Content Security Policy)
- [ ] Enable secure cookie settings
- [ ] Set up monitoring and logging

### Environment Configuration
```bash
# Production environment variables
NEXTAUTH_URL=https://your-domain.com
NEXTAUTH_SECRET=your-secure-random-secret
KEYCLOAK_ISSUER=https://your-keycloak-domain.com/realms/openmemory
```

## Troubleshooting

### Common Issues

1. **Infinite Redirect Loop**:
   - Check NEXTAUTH_URL configuration
   - Verify Keycloak redirect URIs
   - Check middleware configuration

2. **Token Not Included in API Calls**:
   - Verify API client configuration
   - Check session token availability
   - Review axios interceptor setup

3. **Sign-in Fails**:
   - Check Keycloak client configuration
   - Verify KEYCLOAK_ISSUER URL
   - Check network connectivity to Keycloak

### Debugging
- Check browser developer tools for errors
- Review Next.js server logs
- Verify Keycloak client settings
- Test authentication flow manually

### Keycloak Client Configuration
For the UI client in Keycloak:
- **Client Type**: Public
- **Valid redirect URIs**: `http://localhost:3000/api/auth/callback/keycloak`
- **Valid post logout redirect URIs**: `http://localhost:3000`
- **Web origins**: `http://localhost:3000`

## API Integration

### Authenticated Requests
All API requests automatically include the Bearer token:
```typescript
// Using the authenticated API client
import apiClient from '@/lib/api-client';

const response = await apiClient.get('/api/v1/memories');
// Token automatically included in Authorization header
```

### Error Handling
- 401 errors automatically redirect to sign-in
- Token refresh handled transparently
- Network errors properly handled and displayed

## Monitoring and Analytics

### Authentication Events
- Track sign-in/sign-out events
- Monitor authentication failures
- Log security-related events
- Set up alerts for suspicious activity

### Performance Monitoring
- Track authentication flow performance
- Monitor token refresh frequency
- Measure sign-in completion rates
- Track session duration