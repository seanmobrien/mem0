# Multi-stage build for certbot-azure container
# Stage 1: Builder - Install dependencies
FROM certbot/certbot:latest AS builder

# Install build dependencies
USER root
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    python3-dev \
    py3-pip \
    openssl

# Install certbot-dns-desec plugin (latest version)
RUN pip install --no-cache-dir certbot-dns-desec

# Stage 2: Runner - Final image
FROM certbot/certbot:latest

LABEL org.opencontainers.image.name="openmemory/certbot-azure"
LABEL org.opencontainers.image.description="Certbot with deSEC DNS challenge and Azure Key Vault integration"
LABEL org.opencontainers.image.source="https://github.com/seanmobrien/mem0"

# Install runtime dependencies
USER root
RUN apk add --no-cache \
    bash \
    curl \
    ca-certificates \
    python3 \
    py3-pip \
    jq \
    openssl

# Copy certbot-dns-desec from builder
COPY --from=builder /opt/certbot/lib/python3.12/site-packages/certbot_dns_desec* /opt/certbot/lib/python3.12/site-packages/
COPY --from=builder /opt/certbot/lib/python3.12/site-packages/lexicon* /opt/certbot/lib/python3.12/site-packages/

# Install Azure CLI (latest version)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev && \
    pip install --no-cache-dir --break-system-packages azure-cli && \
    apk del gcc musl-dev python3-dev libffi-dev

# Create non-root user for running the application
RUN addgroup -g 1000 certbot && \
    adduser -D -u 1000 -G certbot certbot

# Create mount point for secrets output
RUN mkdir -p /mnt/secrets-output && \
    chown certbot:certbot /mnt/secrets-output

# Create directory for certbot work
RUN mkdir -p /var/lib/letsencrypt && \
    mkdir -p /var/log/letsencrypt && \
    mkdir -p /etc/letsencrypt && \
    chown -R certbot:certbot /var/lib/letsencrypt /var/log/letsencrypt /etc/letsencrypt

# Copy the certificate management script
COPY --chown=certbot:certbot certbot-azure.sh /usr/local/bin/certbot-azure.sh
RUN chmod +x /usr/local/bin/certbot-azure.sh

# Switch to non-root user
USER certbot

# Set working directory
WORKDIR /home/certbot

# Default command runs the certificate management script
CMD ["/usr/local/bin/certbot-azure.sh"]
