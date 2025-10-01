# Flagsmith Deployment (Azure Container Apps)

This directory packages a production-ready Flagsmith instance for the OpenMemory platform. The Dockerfile is now a thin wrapper around the official Flagsmith unified image so you can pin a release and supply Azure Container Apps (ACA) configuration at deploy time.

## Dockerfile Highlights

- **Official base image:** Uses `docker.flagsmith.com/flagsmith/flagsmith:${FLAGSMITH_TAG}` for a single image that serves the API, task processor, and dashboard UI.
- **Configurable tag:** Override the version during `docker build` with `--build-arg FLAGSMITH_TAG=vX.Y.Z` to align with your rollout cadence.
- **Upstream entrypoint:** Reuses Flagsmith’s default startup script (Gunicorn + migrations helper). Any runtime settings should be provided via environment variables instead of custom build steps.
- **Health endpoint compatibility:** The upstream image exposes `/health/` and `/healthz/` which can be wired to ACA readiness probes.

## Backing Services & Core Environment Variables

Flagsmith requires PostgreSQL and Redis in production. Provision managed instances for each service and surface the connection details to the container through ACA secrets:

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | ✅ | PostgreSQL connection string (`postgres://user:pass@host:5432/dbname`). |
| `REDIS_URL` | ✅ | Redis connection string used for asynchronous tasks and caching. |
| `DJANGO_SECRET_KEY` | ✅ | 50+ character secret for Django cryptographic signing. Store this as an ACA secret. |
| `DJANGO_ALLOWED_HOSTS` | ✅ | Comma-separated hostnames that should serve the app (e.g. your ACA FQDN + custom domains). |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | ⚠️ | Required when serving the dashboard over HTTPS on a custom domain. |
| `FLAGSMITH_DOMAIN` | ⚙️ | Domain used in system generated emails and links. |
| `ENABLE_TELEMETRY` | ⚙️ | Set to `false` to opt out of anonymous self-host telemetry. Defaults to `true`. |

The Flagsmith documentation maintains an exhaustive list of optional settings (application behaviour, email, security, caching, integrations, etc.). Review the following sections and mirror any required values as ACA secrets:

- [Deployment → Hosting → API → Environment Variables](https://docs.flagsmith.com/deployment/hosting/locally-api#environment-variables)
- [Deployment → Hosting → Frontend](https://docs.flagsmith.com/deployment/hosting/locally-frontend) (UI-specific overrides)
- [Deployment → Configuration](https://docs.flagsmith.com/deployment/configuration/) (advanced tuning and enterprise features)

## Database Migrations & Static Assets

Run migrations whenever the container image is upgraded. The upstream image includes Django tooling, so you can execute the following as an ACA job or a one-shot container using the same environment variables as the main workload:

```sh
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

For larger installations, schedule these commands as part of your deployment pipeline to ensure the database schema stays in sync before traffic reaches new replicas.

## Azure Container Apps Guidance

- **Container port:** The image exposes port `8000`; configure ACA ingress to forward external traffic to `8000`.
- **Scale profile:** Start with `minReplicas=1`, `maxReplicas=3`, `cpuUtilization=70`, and allocate at least `2 GiB` memory per replica.
- **Secrets management:** Store Postgres, Redis, and Django secrets using ACA Secrets and map them to the environment variables above.
- **Ingress:** Enable external ingress, bind custom hostnames, and provision managed TLS certificates.
- **Startup command:** Leave the Dockerfile entrypoint untouched. ACA will run the upstream Flagsmith entrypoint so migrations and Gunicorn start automatically.

## Additional Tips

- Monitor ACA logs (`az containerapp logs show`) for Django startup output, telemetry notices, and migration status.
- Flagsmith exposes `/health/` (application) and `/healthz/` (infrastructure) endpoints; wire them to ACA probes for faster failure detection.
- For background jobs (e.g. segment exports) reuse ACA jobs or Functions that call the Flagsmith API using service accounts configured in the same environment.
- If you need to enable email flows, configure the appropriate `EMAIL_*` variables documented upstream and verify that the `django_site` table contains your external domain.
