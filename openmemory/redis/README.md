# Redis Container with TLS Support

This directory contains the Redis container setup with TLS (Transport Layer Security) support for the OpenMemory application.

## Overview

This setup provides a Redis instance running in a Docker container with TLS encryption enabled. It uses the Redis Stack Server as the base image and includes custom configuration for secure connections.

## Features

- **Base Image**: Built on `redis/redis-stack-server:latest`
- **TLS Support**: Automatic TLS certificate setup and configuration
- **Password Authentication**: Secure password-based authentication
- **Docker Secrets**: Support for Docker secrets to manage sensitive data
- **Port Configuration**: Exposes both non-TLS (16379) and TLS (16380) ports
- **Sysctl Optimization**: Attempts to set `vm.overcommit_memory=1` for better performance

## Prerequisites

- Docker installed and running
- OpenSSL for certificate generation (if creating self-signed certificates)

## Configuration

### Required Secrets

The following secret files must be created in the `secrets/` directory:

- `REDIS_PW`: Contains the Redis password (plain text, one line)
- `REDIS_CERT`: Contains the TLS certificate (PEM format)
- `REDIS_CERT_PW`: Contains the password for the TLS certificate private key (if encrypted)

### Environment Variables (Optional)

The container supports the following environment variables for customization:

- `REDIS_PASSWORD_FILE`: Path to password file (default: `/run/secrets/REDIS_PW`)
- `REDIS_PORT`: Non-TLS port (default: `16379`)
- `REDIS_TLS_PORT`: TLS port (default: `16380`)
- `REDIS_TLS_DIR`: Directory for TLS files (default: `/data/tls`)
- `REDIS_CERT_FILE`: Path to certificate file (default: `/run/secrets/REDIS_CERT`)
- `REDIS_CERT_PW_FILE`: Path to certificate password file (default: `/run/secrets/REDIS_CERT_PW`)

## Building the Image

To build the Docker image:

```bash
cd openmemory/redis
docker build -t redis:school-lawyer .
```

## Running the Container

### Using the Run Script

The provided `run-docker.sh` script simplifies running the container:

```bash
cd openmemory/redis
# Run in detached mode (default)
./run-docker.sh
# Or run interactively
./run-docker.sh interactive
```

The script will:
- Check for the required Docker image and secret files
- Stop and remove any existing container with the same name
- Run the container with appropriate sysctl settings and port mappings

### Manual Docker Run

If you prefer to run manually:

```bash
docker run -d \
  --name school-law-redis \
  -p 16379:16379 \
  -p 16380:16380 \
  -v ./secrets/REDIS_PW:/run/secrets/REDIS_PW:ro \
  -v ./secrets/REDIS_CERT:/run/secrets/REDIS_CERT:ro \
  -v ./secrets/REDIS_CERT_PW:/run/secrets/REDIS_CERT_PW:ro \
  --sysctl vm.overcommit_memory=1 \
  redis:school-lawyer
```

## TLS Configuration

### Certificate Requirements

The TLS certificate should be in PEM format and include the full certificate chain. The private key can be encrypted with a password.

### Generating Self-Signed Certificates (Development Only)

For development purposes, you can generate self-signed certificates:

```bash
# Create TLS directory
mkdir -p secrets

# Generate private key
openssl genrsa -aes256 -out secrets/redis.key 2048

# Generate certificate signing request
openssl req -new -key secrets/redis.key -out secrets/redis.csr

# Generate self-signed certificate
openssl x509 -req -days 365 -in secrets/redis.csr -signkey secrets/redis.key -out secrets/redis.crt

# Create CA certificate (copy of the certificate for self-signed)
cp secrets/redis.crt secrets/redis.ca.crt

# Set certificate password (if key is encrypted)
echo "your_certificate_password" > secrets/REDIS_CERT_PW

# Copy certificate to expected location
cp secrets/redis.crt secrets/REDIS_CERT
```

**Note**: Self-signed certificates should only be used for development. For production, use certificates from a trusted Certificate Authority.

### Connecting to Redis

- **Non-TLS**: Connect to `localhost:16379` (requires password authentication)
- **TLS**: Connect to `localhost:16380` using TLS (requires client certificate configuration)

## Troubleshooting

- Ensure all required secret files exist in the `secrets/` directory
- Check Docker logs: `docker logs school-law-redis`
- Verify ports are not in use by other services
- For TLS issues, ensure certificates are valid and properly formatted</content>
<parameter name="filePath">/home/seanm/repos/mem0/openmemory/redis/README.md