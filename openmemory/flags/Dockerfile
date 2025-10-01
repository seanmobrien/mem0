# syntax=docker/dockerfile:1.7

###
# Builder stage: grab the Flagsmith release and install dependencies
###
ARG FLAGSMITH_VERSION=9.3.0
FROM python:3.12-slim AS backend-builder
ARG FLAGSMITH_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       build-essential \
       git \
       curl \
       wget \
       libpq-dev \
       nodejs \
       npm \
  && npm install --global yarn \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/flagsmith
RUN wget -O flagsmith.tar.gz \
      "https://github.com/Flagsmith/flagsmith/archive/refs/tags/v${FLAGSMITH_VERSION}.tar.gz" \
  && tar -xf flagsmith.tar.gz --strip-components=1 \
  && rm flagsmith.tar.gz

# Install Python dependencies
RUN python -m venv /opt/venv \
  && . /opt/venv/bin/activate \
  && pip install --upgrade pip \
  && pip install -r api/requirements/production.txt

# Build frontend assets
WORKDIR /opt/flagsmith/frontend
RUN yarn install --frozen-lockfile \
  && yarn build

###
# Runtime image
###
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLAGSMITH_ENV=production \
    DJANGO_SETTINGS_MODULE=app.settings.production \
    DJANGO_ALLOWED_HOSTS=flags.jollybush-836e15bc.westus3.azurecontainerapps.io

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       libpq5 \
       libffi8 \
       libssl3 \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --system --uid 1001 --create-home --shell /usr/sbin/nologin flagsmith

# Copy Python venv and application code
COPY --from=backend-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app
COPY --from=backend-builder /opt/flagsmith/api /app/api
COPY --from=backend-builder /opt/flagsmith/frontend/public /app/public
COPY --from=backend-builder /opt/flagsmith/frontend/build /app/frontend_build
COPY --from=backend-builder /opt/flagsmith/docker/django/entrypoint.sh /app/entrypoint.sh

# Collect static assets and apply migrations at runtime
RUN chmod +x /app/entrypoint.sh \
  && mkdir -p /data/media \
  && chown -R flagsmith:flagsmith /app /data

USER flagsmith

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -f http://127.0.0.1:8000/health/ || exit 1

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
CMD ["gunicorn", "app.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]