ARG FLAGSMITH_TAG=latest
ARG LOG_LVL=ERROR
ARG ALLOWED_HOSTS="flags.obapps.net"
ARG CSRF_TRUSTED_ORIGINS="login.obapps.net,mem0-api.compliance-theater.obapps.net,mem0-ui.compliance-theater.obapps.net,full-ui.compliance-theater.obapps.net"

FROM docker.flagsmith.com/flagsmith/flagsmith:${FLAGSMITH_TAG}

ARG FLAGSMITH_TAG=${FLAGSMITH_TAG}
ARG LOG_LVL=${LOG_LVL}
ARG ALLOWED_HOSTS=${ALLOWED_HOSTS}
ARG CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS}


# This image contains the full Flagsmith stack (API + frontend) and is maintained by
# the Flagsmith team. Customize runtime configuration exclusively through environment
# variables documented at:
# API: https://docs.flagsmith.com/deployment/locally-api#environment-variables
# UI:  https://docs.flagsmith.com/deployment/locally-frontend#environment-variables

# Override FLAGSMITH_TAG at build time if you need a pinned release, e.g.:
#   docker build --build-arg FLAGSMITH_TAG=2.197.0 -t flagsmith .

#ENV DATABASE_URL=${SECRET_DB_URL}
ENV LOG_LEVEL=${LOG_LVL}
#ENV DJANGO_SECRET_KEY=${SECRET_FLAGSMITH_KEY}
ENV ORGANISATION_NAME="Compliance-Theatre"
ENV PROJECT_NAME="web-ui"
ENV ENABLE_GZIP_COMPRESSION=true
#ENV ALLOW_REGISTRATION_WITHOUT_INVITE=0
ENV APPLICATION_INSIGHTS_CONNECTION_STRING=${APPLICATION_INSIGHTS_CONNECTION_STRING}
ENV RESTRICT_ORG_CREATE_TO_SUPERUSERS=true
ENV ENABLE_API_USAGE_TRACKING=true
ENV USE_CACHE_FOR_USAGE_DATA=true
#ENV DJANGO_ALLOWED_HOSTS=${ALLOWED_HOSTS}
#ENV DJANGO_CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS}
ENV CACHE_ENVIRONMENT_DOCUMENT_MODE="PERSISTENT"
ENV CACHE_ENVIRONMENT_DOCUMENT_BACKEND="django_redis.cache.RedisCache"
#ENV CACHE_ENVIRONMENT_DOCUMENT_LOCATION=${SECRET_REDIS_URL}
ENV CACHE_ENVIRONMENT_DOCUMENT_OPTIONS="{\"KEY_PREFIX\": \"feature-flags:\" }"
ENV TIMEOUT=600
#ENV FLAGSMITH_API_URL="https://${ALLOWED_HOSTS}/api/v1/"
#ENV FLAGSMITH_ON_FLAGSMITH_API_KEY=${SECRET_FLAGSMITH_ON_FLAGSMITH_API_KEY}
#ENV FLAGSMITH_ON_FLAGSMITH_API_URL="https://${ALLOWED_HOSTS}/api/v1/"
ENV COOKIE_SAME_SITE=Lax
ENV LOGGING_LOG_LEVEL=${LOG_LVL}

EXPOSE 8000