# Flagsmith Deployment (Azure Container Apps)

This directory packages a production-ready Flagsmith instance for the OpenMemory platform. The accompanying Dockerfile builds a fully self-hosted environment designed to run inside Azure Container Apps (ACA).

## Dockerfile Highlights

- **Pinned release:** Downloads a tagged Flagsmith release archive. Override the version by passing `--build-arg FLAGSMITH_VERSION=x.y.z` during `docker build`.
- **Two-phase build:** Compiles the React frontend in a dedicated builder stage so the runtime image only serves the prebuilt assets and Python backend.
- **Azure host defaults:** Sets `DJANGO_ALLOWED_HOSTS` to the ACA hostname (`flags.jollybush-836e15bc.westus3.azurecontainerapps.io`) baked into the image; override at runtime if you expose a different hostname.
- **Non-root runtime:** Switches to a `flagsmith` system user (`UID 1001`) before launching Gunicorn, aligning with container security best practices.
- **Health probe:** Provides a `/health/` HTTP endpoint that ACA can monitor using the Dockerfile `HEALTHCHECK`.

## Environment & Backing Services

Flagsmith requires PostgreSQL and Redis for production workloads. Configure the following environment variables (and secrets) inside your ACA environment:

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string (`postgres://user:pass@host:5432/dbname`). |
| `REDIS_URL` | Redis connection string (`redis://user:pass@host:6379/0`). |
| `DJANGO_SECRET_KEY` | 50+ character secret for Django cryptographic signing. Store in ACA secrets. |
| `DJANGO_ALLOWED_HOSTS` | Optional override of the hostname baked into the image. |
| `FLAGSMITH_DJANGO_DEBUG` | Set to `false` in production. |
| `FLAGSMITH_API_URL` | Optional external API URL for standalone frontends. |
| `FLAGSMITH_SELF_HOSTED` | Set to `true` to enable the Flagsmith admin UI for self-hosting. |
| `AWS_*` | Only required if using S3-compatible storage for uploaded files. |

After the container starts for the first time, run Django migrations to initialize the schema:

```sh
# Example: run once as an ACA job or init container
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Ensure the job uses the same environment variables and secrets as the main container so it can connect to PostgreSQL and Redis.

## Azure Container Apps Guidance

- **Container port:** The image exposes port `8000`; configure ACA ingress to forward external traffic to `8000`.
- **Scale profile:** Start with `minReplicas=1`, `maxReplicas=3`, `cpu=70%` utilization target, and allocate at least `2 GiB` memory per replica.
- **Secrets management:** Store database, cache, and Django secrets using ACA Secrets and reference them as environment variables.
- **Ingress:** Enable external ingress, bind the custom hostname, and provision a managed TLS certificate.
- **Startup command:** Leave the Dockerfile entrypoint as-is; ACA will execute Gunicorn via `/app/entrypoint.sh`.

## Additional Tips

- Monitor ACA logs (`az containerapp logs show`) for Django startup output and migration status.
- For background jobs (e.g., syncing segments), consider using ACA jobs or Azure Functions hitting the Flagsmith API.
- If you need to tweak static asset handling, update the builder stage to adjust the `frontend` build or the `entrypoint.sh` script copied from Flagsmith upstream.
