# Testing Plan for certbot-azure

This document outlines the testing procedures for the certbot-azure container.

## Prerequisites for Testing

1. **deSEC Account**
   - Register at https://desec.io
   - Create a domain and obtain API token
   - Configure domain nameservers to point to deSEC

2. **Azure Resources**
   - Azure subscription
   - Service principal with Key Vault permissions
   - Existing Azure Key Vault
   - Note: Tenant ID, Client ID, Client Secret

3. **Local Environment**
   - Docker installed and running
   - Network access to:
     - Let's Encrypt ACME servers
     - deSEC API
     - Azure services
     - Alpine package repositories

## Build Tests

### Test 1: Docker Build
```bash
cd openmemory/certbot-azure
docker build -t test-certbot-azure .
```

**Expected Result:**
- Build completes successfully
- No errors during package installation
- certbot-dns-desec plugin installed
- Azure CLI installed
- Image size is reasonable (< 1GB)

**Verification:**
```bash
docker images test-certbot-azure
docker run --rm test-certbot-azure certbot --version
docker run --rm test-certbot-azure az --version
docker run --rm test-certbot-azure pip list | grep certbot-dns-desec
```

### Test 2: Security Scan
```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image test-certbot-azure
```

**Expected Result:**
- No critical or high severity vulnerabilities
- Container runs as non-root user
- Minimal attack surface

## Functional Tests

### Test 3: Script Validation
```bash
# Test help/error handling
docker run --rm test-certbot-azure

# Expected: Error message about missing parameters
```

### Test 4: Staging Certificate Request
**Setup:**
1. Copy `.env.example` to `.env`
2. Fill in all required values
3. Set `CERTMGR_STAGING=true`

```bash
./run-example.sh
```

**Expected Result:**
- Script starts successfully
- Connects to deSEC API
- Creates DNS TXT records
- Validates domain ownership
- Receives staging certificate from Let's Encrypt
- Writes certificates to `/mnt/secrets-output`
- Authenticates with Azure
- Uploads certificate to Azure Key Vault
- Success audit log written to console
- Container exits cleanly

**Verification:**
```bash
ls -la certs/
# Should contain: cert.pem, chain.pem, fullchain.pem, privkey.pem

openssl x509 -in certs/fullchain.pem -text -noout
# Should show Let's Encrypt Staging certificate

az keyvault certificate show \
  --vault-name <your-vault> \
  --name <your-cert-name>
# Should show certificate in Key Vault
```

### Test 5: Production Certificate Request
**Setup:**
1. Set `CERTMGR_STAGING=false` in `.env`
2. Ensure domain is properly configured

```bash
./run-example.sh
```

**Expected Result:**
- Same as Test 4, but with production certificate
- Certificate is trusted by browsers

**Verification:**
```bash
openssl x509 -in certs/fullchain.pem -text -noout
# Should show Let's Encrypt production certificate (no "Staging" in issuer)
```

### Test 6: Certificate Renewal
**Setup:**
1. Set `CERTMGR_RENEWAL_MODE=true` in `.env`

```bash
./run-example.sh
```

**Expected Result:**
- Force renewal of existing certificate
- New certificate replaces old one
- Azure Key Vault updated with new certificate

**Verification:**
```bash
openssl x509 -in certs/fullchain.pem -text -noout | grep "Not After"
# Compare timestamp with previous certificate
```

### Test 7: Wildcard Certificate
**Setup:**
1. Set `CERTMGR_DOMAIN=*.example.com` in `.env`
2. Set `CERTMGR_STAGING=true`

```bash
./run-example.sh
```

**Expected Result:**
- Successfully requests wildcard certificate
- Certificate covers `*.example.com`

**Verification:**
```bash
openssl x509 -in certs/fullchain.pem -text -noout | grep DNS
# Should show: DNS:*.example.com
```

### Test 8: Multiple Domains
**Setup:**
1. Set `CERTMGR_DOMAIN="example.com,www.example.com,api.example.com"`

```bash
./run-example.sh
```

**Expected Result:**
- Certificate covers all specified domains

**Verification:**
```bash
openssl x509 -in certs/fullchain.pem -text -noout | grep DNS
# Should show all domains
```

### Test 9: Ephemeral Volume
**Setup:**
1. Run without mounting a volume

```bash
docker run --rm \
  -e CERTMGR_DOMAIN=test.example.com \
  -e CERTMGR_EMAIL=admin@example.com \
  -e CERTMGR_DESEC_TOKEN=<token> \
  -e CERTMGR_AZURE_TENANT_ID=<tenant> \
  -e CERTMGR_AZURE_CLIENT_ID=<client> \
  -e CERTMGR_AZURE_CLIENT_SECRET=<secret> \
  -e CERTMGR_AZURE_KEYVAULT_NAME=<vault> \
  -e CERTMGR_AZURE_CERT_NAME=<cert> \
  -e CERTMGR_STAGING=true \
  test-certbot-azure
```

**Expected Result:**
- Container creates ephemeral directory
- Certificate uploaded to Azure Key Vault
- Container exits successfully
- No local certificates retained

### Test 10: Keep-Alive Mode
**Setup:**
1. Set `CERTMGR_KEEPALIVE=true`

```bash
docker run -it --rm \
  -e CERTMGR_KEEPALIVE=true \
  -e CERTMGR_STAGING=true \
  [other env vars...] \
  test-certbot-azure
```

**Expected Result:**
- Certificate operations complete
- Container drops into bash shell
- Can inspect logs, certificates manually

**Verification:**
```bash
# Inside container:
ls -la /mnt/secrets-output
cat /var/log/letsencrypt/letsencrypt.log
```

## CI/CD Tests

### Test 11: GitHub Actions Workflow
**Trigger:**
1. Push changes to `openmemory/certbot-azure/**`
2. Monitor workflow: `.github/workflows/deployment-certbot-azure.yml`

**Expected Result:**
- Workflow triggers automatically
- Docker image builds successfully
- Image pushed to Azure Container Registry
- Metadata artifact created
- Build summary appears in GitHub Actions

### Test 12: Matrix Build Integration
**Trigger:**
1. Manual workflow dispatch of `openmemory-docker.yml`

**Expected Result:**
- certbot-azure included in service matrix
- Builds alongside other OpenMemory services

## Error Handling Tests

### Test 13: Invalid deSEC Token
**Setup:**
1. Set `CERTMGR_DESEC_TOKEN=invalid_token`

```bash
./run-example.sh
```

**Expected Result:**
- Clear error message about deSEC authentication
- Container exits with error code
- Error logged to console

### Test 14: Azure Authentication Failure
**Setup:**
1. Set `CERTMGR_AZURE_CLIENT_SECRET=invalid_secret`

```bash
./run-example.sh
```

**Expected Result:**
- Certificate obtained successfully
- Azure authentication fails with clear error
- Error logged to console
- Container exits with error code

### Test 15: Missing Required Parameters
**Setup:**
1. Remove `CERTMGR_DOMAIN` from `.env`

```bash
./run-example.sh
```

**Expected Result:**
- Clear error message listing missing parameters
- Usage instructions displayed
- Container exits with error code

### Test 16: Invalid Domain
**Setup:**
1. Set `CERTMGR_DOMAIN=notconfigured.example.com`

```bash
./run-example.sh
```

**Expected Result:**
- DNS challenge fails
- Clear error message
- Container exits with error code

## Docker Compose Tests

### Test 17: Docker Compose Build
```bash
cd openmemory
docker-compose build certbot-azure
```

**Expected Result:**
- Image builds successfully
- No errors

### Test 18: Docker Compose Run with Profile
```bash
cd openmemory
docker-compose --profile certbot up certbot-azure
```

**Expected Result:**
- Service starts with environment variables from `.env`
- Completes certificate operations
- Service exits

## Performance Tests

### Test 19: Build Time
```bash
time docker build -t test-certbot-azure openmemory/certbot-azure/
```

**Expected Result:**
- Build completes in < 10 minutes
- Cached builds complete in < 1 minute

### Test 20: Run Time
```bash
time ./run-example.sh
```

**Expected Result:**
- Staging certificate: < 5 minutes
- Production certificate: < 5 minutes
- DNS propagation accounts for majority of time

## Cleanup

After testing:

1. Delete staging/test certificates from Let's Encrypt:
   - Staging certificates expire automatically
   - No action needed

2. Clean up Azure Key Vault:
   ```bash
   az keyvault certificate delete --vault-name <vault> --name <cert>
   az keyvault certificate purge --vault-name <vault> --name <cert>
   ```

3. Remove test domain from deSEC:
   - Via deSEC web interface

4. Remove local test images:
   ```bash
   docker rmi test-certbot-azure
   docker system prune -f
   ```

## Test Results Template

| Test # | Test Name | Status | Notes |
|--------|-----------|--------|-------|
| 1 | Docker Build | ☐ Pass / ☐ Fail | |
| 2 | Security Scan | ☐ Pass / ☐ Fail | |
| 3 | Script Validation | ☐ Pass / ☐ Fail | |
| 4 | Staging Certificate | ☐ Pass / ☐ Fail | |
| 5 | Production Certificate | ☐ Pass / ☐ Fail | |
| 6 | Certificate Renewal | ☐ Pass / ☐ Fail | |
| 7 | Wildcard Certificate | ☐ Pass / ☐ Fail | |
| 8 | Multiple Domains | ☐ Pass / ☐ Fail | |
| 9 | Ephemeral Volume | ☐ Pass / ☐ Fail | |
| 10 | Keep-Alive Mode | ☐ Pass / ☐ Fail | |
| 11 | GitHub Actions | ☐ Pass / ☐ Fail | |
| 12 | Matrix Build | ☐ Pass / ☐ Fail | |
| 13 | Invalid deSEC Token | ☐ Pass / ☐ Fail | |
| 14 | Azure Auth Failure | ☐ Pass / ☐ Fail | |
| 15 | Missing Parameters | ☐ Pass / ☐ Fail | |
| 16 | Invalid Domain | ☐ Pass / ☐ Fail | |
| 17 | Docker Compose Build | ☐ Pass / ☐ Fail | |
| 18 | Docker Compose Run | ☐ Pass / ☐ Fail | |
| 19 | Build Time | ☐ Pass / ☐ Fail | |
| 20 | Run Time | ☐ Pass / ☐ Fail | |

## Known Limitations

1. **Network Requirements**: Requires internet access to:
   - Alpine package repositories
   - PyPI for Python packages
   - Let's Encrypt ACME servers
   - deSEC API
   - Azure services

2. **Rate Limits**: Let's Encrypt has rate limits:
   - 50 certificates per registered domain per week
   - Use staging environment for testing

3. **DNS Propagation**: May take 60-120 seconds for DNS changes to propagate

4. **Azure Permissions**: Service principal must have appropriate Key Vault permissions
