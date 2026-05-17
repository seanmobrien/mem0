# Certbot Azure - Let's Encrypt certificate manager with deSEC and Azure Key Vault
FROM certbot/certbot:latest

LABEL org.opencontainers.image.name="openmemory/certbot-azure"
LABEL org.opencontainers.image.description="Certbot with deSEC/Cloudflare DNS challenge and Azure Key Vault integration"
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
    # build wheels for our Python dependencies (include Cloudflare python lib)
    retry python3 -m pip wheel --no-cache-dir --wheel-dir /wheels certbot-dns-desec certbot-dns-cloudflare==1.1.0 cloudflare==2.3.1  certbot-dns-freedns azure-cli; \
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
    retry apk add --no-cache bash curl ca-certificates jq openssl bind-tools
    # Update package repositories and install runtime dependencies

# Copy the certificate management script (keep owned by root; entrypoint will run it as certbot-user)
COPY certbot-azure.sh /usr/local/bin/certbot-azure.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh 

# install from local wheels to avoid network and compilation in final image
COPY --from=builder /wheels /wheels
# Install Python packages from wheels produced in the builder stage
# Create non-root user for running the application
# Create mount point for secrets output (ownership may be adjusted at runtime by entrypoint)
# Create directory for certbot work
# Install su-exec (small tool to drop privileges cleanly) and copy entrypoint
# su-exec is available in Alpine; ensure package repo updated earlier
RUN addgroup -g 1000 certbot-user && \
    adduser -D -u 1000 -G certbot-user certbot-user; \
    set -eux; \
    python3 -m pip install --no-cache-dir /wheels/*.whl; \
    rm -rf /wheels; \
    (mkdir -p /mnt/secrets-output /var/log/letsencrypt /var/lib/letsencrypt /etc/letsencrypt || true) && \    
    (chown -R certbot-user:certbot-user /mnt/secrets-output /var/lib/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt /etc/letsencrypt || true) && \
    (chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/certbot-azure.sh || true) && \    
    (apk add --no-cache su-exec || true)

# Keep running as root for the entrypoint which can chown mounts; entrypoint will drop privileges
WORKDIR /home/certbot-user
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/usr/local/bin/certbot-azure.sh"]
