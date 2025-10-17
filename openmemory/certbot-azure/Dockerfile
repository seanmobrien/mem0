# Certbot Azure - Let's Encrypt certificate manager with deSEC and Azure Key Vault
FROM certbot/certbot:latest

LABEL org.opencontainers.image.name="openmemory/certbot-azure"
LABEL org.opencontainers.image.description="Certbot with deSEC DNS challenge and Azure Key Vault integration"
LABEL org.opencontainers.image.source="https://github.com/seanmobrien/mem0"

# Switch to root for package installation
USER root

# Builder stage: produce wheels for Python packages on an Alpine-based Python image
FROM python:3.12-alpine AS builder
RUN set -eux; \
    retry() { n=1; max=5; delay=5; until "$@"; do \
        if [ "$n" -ge "$max" ]; then \
            echo "Command failed after $n attempts: $*"; return 1; \
        fi; \
        sleep_time=$((n * delay)); echo "Command failed, retry #$n in ${sleep_time}s..."; sleep "$sleep_time"; n=$((n+1)); \
    done; \
    }; \
    retry apk update || true; \
    # install build deps needed for wheels
    retry apk add --no-cache build-base gcc musl-dev libffi-dev python3-dev libffi; \
    mkdir -p /wheels; \
    # build wheels for our Python dependencies
    retry python3 -m pip wheel --no-cache-dir --wheel-dir /wheels certbot-dns-desec azure-cli; \
    # clean up build deps in builder (keeps builder small)
    apk del build-base gcc musl-dev libffi-dev python3-dev || true

    # Final stage: start from certbot base again so we can COPY from the builder
    FROM certbot/certbot:latest
    USER root

    # Update package repositories and install runtime dependencies
RUN set -eux; \
    retry() { n=1; max=5; delay=5; until "$@"; do \
        if [ "$n" -ge "$max" ]; then \
            echo "Command failed after $n attempts: $*"; return 1; \
        fi; \
        sleep_time=$((n * delay)); echo "Command failed, retry #$n in ${sleep_time}s..."; sleep "$sleep_time"; n=$((n+1)); \
    done; \
    }; \
    retry apk update || true; \
    retry apk add --no-cache bash curl ca-certificates jq openssl

# Install Python packages from wheels produced in the builder stage
COPY --from=builder /wheels /wheels
RUN set -eux; \
    # install from local wheels to avoid network and compilation in final image
    python3 -m pip install --no-cache-dir /wheels/*.whl; \
    rm -rf /wheels

# Create non-root user for running the application
RUN addgroup -g 1000 certbot-user && \
    adduser -D -u 1000 -G certbot-user certbot-user

# Create mount point for secrets output (ownership may be adjusted at runtime by entrypoint)
RUN mkdir -p /mnt/secrets-output && \
    chown certbot-user:certbot-user /mnt/secrets-output || true

# Create directory for certbot work
RUN mkdir -p /var/lib/letsencrypt && \
    mkdir -p /var/log/letsencrypt && \
    mkdir -p /etc/letsencrypt && \
    chown -R certbot-user:certbot-user /var/lib/letsencrypt /var/log/letsencrypt /etc/letsencrypt

# Copy the certificate management script (keep owned by root; entrypoint will run it as certbot-user)
COPY certbot-azure.sh /usr/local/bin/certbot-azure.sh
RUN chmod +x /usr/local/bin/certbot-azure.sh

# Install su-exec (small tool to drop privileges cleanly) and copy entrypoint
RUN set -eux; \
    # su-exec is available in Alpine; ensure package repo updated earlier
    apk add --no-cache su-exec || true
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Keep running as root for the entrypoint which can chown mounts; entrypoint will drop privileges
WORKDIR /home/certbot-user
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/usr/local/bin/certbot-azure.sh"]
