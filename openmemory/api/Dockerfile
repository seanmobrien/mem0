# Builder stage - Build mem0ai from source
FROM python:3.12-slim AS builder

# Accept build arguments from CI/CD
ARG BUILD_TYPE
ARG GITHUB_REF_NAME
ARG GITHUB_RUN_ID
ARG GITHUB_SHA
ARG GITHUB_ACTOR
ARG GITHUB_WORKFLOW

# Set environment variables for the build script
ENV BUILD_TYPE=${BUILD_TYPE}
ENV GITHUB_ACTIONS=true
ENV GITHUB_REF_NAME=${GITHUB_REF_NAME}
ENV GITHUB_RUN_ID=${GITHUB_RUN_ID}
ENV GITHUB_SHA=${GITHUB_SHA}
ENV GITHUB_ACTOR=${GITHUB_ACTOR}
ENV GITHUB_WORKFLOW=${GITHUB_WORKFLOW}

# Install build dependencies and git for metadata
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install hatch==1.7.0

# Copy mem0ai source code
WORKDIR /src/mem0
COPY --link=true pyproject.toml .
COPY --link=true README.md .
COPY --link=true mem0/ ./mem0/
COPY --link=true build_local.py .

# Build the mem0ai package with CI/CD metadata
RUN python build_local.py

# Runner stage - OpenMemory API
FROM python:3.12-slim AS runner

LABEL org.opencontainers.image.name="mem0/openmemory-mcp"

WORKDIR /usr/src/openmemory

# Install runtime dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
# Ensure pip/setuptools/wheel are present so pkg_resources is available at runtime
RUN python -m pip install --upgrade pip setuptools wheel

# Copy the built mem0ai package from builder stage
COPY --from=builder --link=true /src/mem0/dist/*.whl /tmp/

# Copy and install requirements first (better caching for development)
COPY --link=true openmemory/api/requirements.txt .
RUN pip install /tmp/*.whl && \
    rm -rf /tmp/*.whl && \
    pip install -r requirements.txt && \
    mkdir -p /mnt/db && \
    chmod 755 /mnt/db && \
    adduser --disabled-password --gecos '' --uid 1000 appuser && \
    chown -R appuser:appuser /usr/src/openmemory /mnt/db

# Install test dependencies and run tests before final image
COPY --link=true openmemory/api/requirements-test.txt .
COPY --link=true openmemory/api/ .
COPY --link=true tests/ ./tests/
RUN pip install -r requirements-test.txt && pytest tests && rm -rf tests/ && find . -type f -name 'test_*.py' -delete

# Fix ownership of copied files and switch to non-root user
RUN chown -R appuser:appuser /usr/src/openmemory
USER appuser

# Set default log level (can be overridden with environment variable)
ENV LOG_LEVEL=warning

EXPOSE 8765

# Add health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8765/api/v1/stats/health-check || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8765 --no-server-header --forwarded-allow-ips '*' --log-level ${LOG_LEVEL}"]
