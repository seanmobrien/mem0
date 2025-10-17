# Certbot Azure - Let's Encrypt Certificate Manager

Docker container for automated Let's Encrypt certificate management with deSEC DNS challenge and Azure Key Vault integration.

## Overview

This container provides a complete solution for:
- Requesting Let's Encrypt SSL/TLS certificates via DNS challenge using deSEC
- Automatically uploading certificates to Azure Key Vault
- Renewing existing certificates
- Writing certificates to local storage (mounted volumes or ephemeral)

## Features

- **Base Image**: Built on official `certbot/certbot` image
- **DNS Challenge**: Uses `certbot-dns-desec` plugin for DNS-01 challenge
- **Azure Integration**: Includes Azure CLI for Key Vault management
- **Security Best Practices**:
  - Multi-stage build (separate build and runtime layers)
  - Runs as non-root user (`certbot:certbot` - UID/GID 1000)
  - Supports Docker secrets for sensitive credentials
  - Minimal attack surface with Alpine Linux base
- **Flexible Configuration**: Parameters or environment variables
- **Volume Support**: Mounted or ephemeral volumes for certificate output

## Prerequisites

1. **deSEC Account**: Register at https://desec.io and obtain an API token
2. **Azure Service Principal**: Create a service principal with permissions to manage Key Vault certificates
3. **Azure Key Vault**: Pre-existing Key Vault where certificates will be stored
4. **Domain**: Domain name configured with deSEC nameservers

## Quick Start

### Using Docker Run

```bash
docker run --rm \
  -v /path/to/certs:/mnt/secrets-output \
  openmemory/certbot-azure \
  example.com \
  admin@example.com \
  desec_api_token_here \
  azure_tenant_id \
  azure_client_id \
  azure_client_secret \
  my-keyvault \
  my-cert-name
```

### Using Environment Variables

```bash
docker run --rm \
  -v /path/to/certs:/mnt/secrets-output \
  -e CERTMGR_DOMAIN=example.com \
  -e CERTMGR_EMAIL=admin@example.com \
  -e CERTMGR_DESEC_TOKEN=desec_api_token \
  -e CERTMGR_AZURE_TENANT_ID=tenant_id \
  -e CERTMGR_AZURE_CLIENT_ID=client_id \
  -e CERTMGR_AZURE_CLIENT_SECRET=client_secret \
  -e CERTMGR_AZURE_KEYVAULT_NAME=my-keyvault \
  -e CERTMGR_AZURE_CERT_NAME=my-cert-name \
  openmemory/certbot-azure
```

### Using Docker Secrets (Recommended for Production)

```bash
# Create secrets
echo "desec_token_here" | docker secret create desec_token -
echo "client_secret_here" | docker secret create azure_client_secret -

# Run with secrets
docker service create \
  --name certbot-azure \
  --secret desec_token \
  --secret azure_client_secret \
  --mount type=volume,source=certs,target=/mnt/secrets-output \
  -e CERTMGR_DOMAIN=example.com \
  -e CERTMGR_EMAIL=admin@example.com \
  -e CERTMGR_DESEC_TOKEN_FILE=/run/secrets/desec_token \
  -e CERTMGR_AZURE_CLIENT_SECRET_FILE=/run/secrets/azure_client_secret \
  openmemory/certbot-azure
```

## Configuration

### Required Parameters/Environment Variables

| Parameter Position | Environment Variable | Description |
|-------------------|---------------------|-------------|
| 1 | `CERTMGR_DOMAIN` | Domain name for certificate |
| 2 | `CERTMGR_EMAIL` | Email for Let's Encrypt registration |
| 3 | `CERTMGR_DESEC_TOKEN` | deSEC API token |
| 4 | `CERTMGR_AZURE_TENANT_ID` | Azure tenant ID |
| 5 | `CERTMGR_AZURE_CLIENT_ID` | Azure client/application ID |
| 6 | `CERTMGR_AZURE_CLIENT_SECRET` | Azure client secret |
| 7 | `CERTMGR_AZURE_KEYVAULT_NAME` | Azure Key Vault name |
| 8 | `CERTMGR_AZURE_CERT_NAME` | Certificate name in Key Vault |

### Optional Parameters/Environment Variables

| Parameter Position | Environment Variable | Default | Description |
|-------------------|---------------------|---------|-------------|
| 9 | `CERTMGR_RENEWAL_MODE` | `false` | Set to `true` to renew existing certificate |
| 10 | `CERTMGR_STAGING` | `false` | Set to `true` to use Let's Encrypt staging environment |
| - | `CERTMGR_KEEPALIVE` | - | Set to `true` to keep container running (launches bash shell) |

## Output Files

When the container runs successfully, the following files are written to `/mnt/secrets-output`:

- `fullchain.pem` - Full certificate chain (certificate + intermediates)
- `privkey.pem` - Private key (chmod 600)
- `cert.pem` - Certificate only
- `chain.pem` - Intermediate certificates only

## Volume Mounting

### With Mounted Volume

```bash
docker run --rm \
  -v /host/path:/mnt/secrets-output \
  openmemory/certbot-azure [parameters...]
```

### Without Mounted Volume (Ephemeral)

If no volume is mounted at `/mnt/secrets-output`, the container will create an ephemeral directory. This is useful for testing or when you only need certificates uploaded to Azure Key Vault.

```bash
docker run --rm openmemory/certbot-azure [parameters...]
```

## Certificate Renewal

To renew an existing certificate, set `CERTMGR_RENEWAL_MODE=true`:

```bash
docker run --rm \
  -v /path/to/certs:/mnt/secrets-output \
  -e CERTMGR_DOMAIN=example.com \
  -e CERTMGR_RENEWAL_MODE=true \
  -e CERTMGR_DESEC_TOKEN=... \
  [other parameters...] \
  openmemory/certbot-azure
```

## Testing with Staging Environment

To test your setup without hitting Let's Encrypt rate limits, use the staging environment:

```bash
docker run --rm \
  -e CERTMGR_STAGING=true \
  -e CERTMGR_DOMAIN=example.com \
  [other parameters...] \
  openmemory/certbot-azure
```

**Note**: Staging certificates are not trusted by browsers and should only be used for testing.

## Keeping Container Alive

For debugging or interactive use, you can keep the container running after certificate operations:

```bash
docker run -it \
  -e CERTMGR_KEEPALIVE=true \
  -e CERTMGR_DOMAIN=example.com \
  [other parameters...] \
  openmemory/certbot-azure
```

The container will drop into a bash shell after completing certificate operations.

## Building the Image

### Local Build

```bash
cd openmemory/certbot-azure
docker build -t openmemory/certbot-azure .
```

### Build with Docker Compose

```bash
docker-compose build certbot-azure
```

## CI/CD Integration

This container integrates with the existing CI/CD pipeline for automatic builds and deployment to Azure Container Registry.

### Automatic Builds

Builds are triggered on:
- Push to `implementation/school-law` or `development` branches
- Changes to `openmemory/certbot-azure/**` files
- Manual workflow dispatch

### Pushing to Azure Container Registry

Images are automatically tagged and pushed to `schoollawregistry.azurecr.io/openmemory-certbot-azure` with:
- Branch name tag (e.g., `development`)
- Short SHA tag (e.g., `abc1234`)
- `latest` tag (for main branch)

## Examples

### Wildcard Certificate

```bash
docker run --rm \
  -v ./certs:/mnt/secrets-output \
  openmemory/certbot-azure \
  "*.example.com" \
  admin@example.com \
  $DESEC_TOKEN \
  $AZURE_TENANT_ID \
  $AZURE_CLIENT_ID \
  $AZURE_CLIENT_SECRET \
  my-keyvault \
  wildcard-cert
```

### Multiple Domains

```bash
docker run --rm \
  -v ./certs:/mnt/secrets-output \
  -e CERTMGR_DOMAIN="example.com,www.example.com,api.example.com" \
  -e CERTMGR_EMAIL=admin@example.com \
  [other environment variables...] \
  openmemory/certbot-azure
```

### Scheduled Renewal (Cron)

Add to crontab for automatic renewal:

```bash
# Renew certificate monthly at 2 AM
0 2 1 * * docker run --rm -v /etc/certs:/mnt/secrets-output -e CERTMGR_RENEWAL_MODE=true [parameters...] openmemory/certbot-azure
```

## Troubleshooting

### DNS Challenge Issues

If DNS challenge fails:
1. Verify deSEC token is valid
2. Ensure domain is configured with deSEC nameservers
3. Check DNS propagation: `dig @ns1.desec.io your-domain.com TXT`
4. Increase propagation wait time if needed (modify Dockerfile)

### Azure Authentication Failures

1. Verify service principal credentials
2. Ensure service principal has `Certificate User` or `Certificate Officer` role on Key Vault
3. Check Azure tenant ID is correct
4. Verify Key Vault name and certificate name

### Permission Errors

Container runs as non-root user (UID 1000). Ensure:
- Mounted volumes are writable by UID 1000
- Host directory has appropriate permissions: `chmod 755 /host/path`

### Viewing Logs

```bash
# With CERTMGR_KEEPALIVE
docker run -it -e CERTMGR_KEEPALIVE=true [parameters...] openmemory/certbot-azure

# Check certbot logs
docker exec -it <container_id> cat /var/log/letsencrypt/letsencrypt.log
```

## Security Considerations

1. **Never commit secrets** to source control
2. **Use Docker secrets** or secure environment variable management in production
3. **Rotate credentials** regularly (deSEC tokens, Azure service principal secrets)
4. **Limit Key Vault permissions** - grant minimum necessary access
5. **Monitor certificate expiry** - Set up automated renewal 30 days before expiry
6. **Use staging environment** for testing to avoid rate limits

## References

- [Certbot Documentation](https://eff-certbot.readthedocs.io/)
- [deSEC API Documentation](https://desec.readthedocs.io/)
- [certbot-dns-desec Plugin](https://github.com/desec-io/certbot-dns-desec)
- [Azure CLI Key Vault Reference](https://docs.microsoft.com/en-us/cli/azure/keyvault/certificate)
- [Let's Encrypt DNS Challenge Guide](https://nerdsniped.se/posts/lets-encrypt-wildcard-certs-with-desec/)

## License

This project follows the same license as the parent mem0 repository (Apache 2.0).

## Support

For issues and questions:
- GitHub Issues: https://github.com/seanmobrien/mem0/issues
- Documentation: See parent repository README
