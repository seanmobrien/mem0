# Certbot-Azure Quick Reference

## One-Line Commands

### Request New Certificate (Staging)
```bash
docker run --rm -v ./certs:/mnt/secrets-output \
  -e CERTMGR_DOMAIN=example.com \
  -e CERTMGR_EMAIL=admin@example.com \
  -e CERTMGR_DESEC_TOKEN=<token> \
  -e CERTMGR_AZURE_TENANT_ID=<tenant-id> \
  -e CERTMGR_AZURE_CLIENT_ID=<client-id> \
  -e CERTMGR_AZURE_CLIENT_SECRET=<secret> \
  -e CERTMGR_AZURE_KEYVAULT_NAME=<vault-name> \
  -e CERTMGR_AZURE_CERT_NAME=<cert-name> \
  -e CERTMGR_STAGING=true \
  openmemory/certbot-azure
```

### Request Production Certificate
```bash
docker run --rm -v ./certs:/mnt/secrets-output \
  [same env vars as above] \
  -e CERTMGR_STAGING=false \
  openmemory/certbot-azure
```

### Renew Existing Certificate
```bash
docker run --rm -v ./certs:/mnt/secrets-output \
  [same env vars as above] \
  -e CERTMGR_RENEWAL_MODE=true \
  openmemory/certbot-azure
```

### Wildcard Certificate
```bash
docker run --rm -v ./certs:/mnt/secrets-output \
  -e CERTMGR_DOMAIN="*.example.com" \
  [other env vars...] \
  openmemory/certbot-azure
```

### Debug Mode (Keep Container Running)
```bash
docker run -it --rm -v ./certs:/mnt/secrets-output \
  [env vars...] \
  -e CERTMGR_KEEPALIVE=true \
  openmemory/certbot-azure
```

## Environment Variables Reference

| Variable | Required | Default | Example |
|----------|----------|---------|---------|
| `CERTMGR_DOMAIN` | Yes | - | `example.com` or `*.example.com` |
| `CERTMGR_EMAIL` | Yes | - | `admin@example.com` |
| `CERTMGR_DESEC_TOKEN` | Yes | - | `your_desec_token` |
| `CERTMGR_AZURE_TENANT_ID` | Yes | - | `xxxxxxxx-xxxx-...` |
| `CERTMGR_AZURE_CLIENT_ID` | Yes | - | `xxxxxxxx-xxxx-...` |
| `CERTMGR_AZURE_CLIENT_SECRET` | Yes | - | `your_secret` |
| `CERTMGR_AZURE_KEYVAULT_NAME` | Yes | - | `my-keyvault` |
| `CERTMGR_AZURE_CERT_NAME` | Yes | - | `my-cert` |
| `CERTMGR_RENEWAL_MODE` | No | `false` | `true` / `false` |
| `CERTMGR_STAGING` | No | `false` | `true` / `false` |
| `CERTMGR_KEEPALIVE` | No | - | `true` / `false` |

## Common Use Cases

### Cron Job for Automatic Renewal (Monthly)
Add to crontab:
```cron
0 2 1 * * docker run --rm -v /etc/certs:/mnt/secrets-output -e CERTMGR_RENEWAL_MODE=true [env vars...] openmemory/certbot-azure >> /var/log/certbot-azure.log 2>&1
```

### Docker Compose Service
```yaml
certbot-azure:
  image: openmemory/certbot-azure:latest
  volumes:
    - certs:/mnt/secrets-output
  environment:
    - CERTMGR_DOMAIN=${CERTMGR_DOMAIN}
    - CERTMGR_EMAIL=${CERTMGR_EMAIL}
    # ... other vars
  profiles:
    - certbot
```

Run with: `docker-compose --profile certbot up certbot-azure`

### Kubernetes CronJob
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: certbot-azure-renewal
spec:
  schedule: "0 2 1 * *"  # Monthly at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: certbot-azure
            image: openmemory/certbot-azure:latest
            env:
            - name: CERTMGR_RENEWAL_MODE
              value: "true"
            - name: CERTMGR_DOMAIN
              valueFrom:
                secretKeyRef:
                  name: certbot-config
                  key: domain
            # ... other env vars from secrets
          restartPolicy: OnFailure
```

## Troubleshooting

### DNS Challenge Fails
```bash
# Check DNS propagation
dig @ns1.desec.io _acme-challenge.example.com TXT

# Verify deSEC token
curl -H "Authorization: Token <your-token>" https://desec.io/api/v1/domains/
```

### Azure Authentication Issues
```bash
# Test Azure CLI login
az login --service-principal \
  --username <client-id> \
  --password <client-secret> \
  --tenant <tenant-id>

# Check Key Vault access
az keyvault certificate list --vault-name <vault-name>
```

### View Container Logs
```bash
# If using keep-alive
docker exec -it <container-id> cat /var/log/letsencrypt/letsencrypt.log

# Or run with keep-alive enabled
docker run -it --rm -e CERTMGR_KEEPALIVE=true [env vars...] openmemory/certbot-azure
```

## Output Files

After successful execution, `/mnt/secrets-output` contains:

- `fullchain.pem` - Full certificate chain (cert + intermediates)
- `privkey.pem` - Private key (chmod 600)
- `cert.pem` - Certificate only
- `chain.pem` - Intermediate certificates

## Security Best Practices

1. **Use Docker Secrets** in production:
   ```bash
   echo "secret" | docker secret create azure_secret -
   docker service create ... --secret azure_secret ...
   ```

2. **Restrict Volume Permissions**:
   ```bash
   chmod 700 /path/to/certs
   chown 1000:1000 /path/to/certs  # Match container user
   ```

3. **Use Staging for Testing**:
   - Always test with `CERTMGR_STAGING=true` first
   - Avoid Let's Encrypt rate limits

4. **Rotate Credentials Regularly**:
   - deSEC API tokens
   - Azure service principal secrets

## Links

- [Full Documentation](README.md)
- [Testing Guide](TESTING.md)
- [deSEC Documentation](https://desec.readthedocs.io/)
- [Let's Encrypt Rate Limits](https://letsencrypt.org/docs/rate-limits/)
- [Azure Key Vault CLI Reference](https://docs.microsoft.com/en-us/cli/azure/keyvault/certificate)
