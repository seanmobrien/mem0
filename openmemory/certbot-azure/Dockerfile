# Certbot Azure - Let's Encrypt certificate manager with deSEC and Azure Key Vault
FROM certbot/certbot:latest

LABEL org.opencontainers.image.name="openmemory/certbot-azure"
LABEL org.opencontainers.image.description="Certbot with deSEC DNS challenge and Azure Key Vault integration"
LABEL org.opencontainers.image.source="https://github.com/seanmobrien/mem0"

# Switch to root for package installation
USER root

# Update package repositories and install runtime dependencies
RUN apk update || true && \
    apk add --no-cache \
    bash \
    curl \
    ca-certificates \
    jq \
    openssl \
    || (sleep 5 && apk add --no-cache bash curl ca-certificates jq openssl)

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    python3-dev \
    || (sleep 5 && apk add --no-cache gcc musl-dev libffi-dev python3-dev)

# Install Python packages
RUN pip install --no-cache-dir certbot-dns-desec || \
    (sleep 5 && pip install --no-cache-dir certbot-dns-desec)

RUN pip install --no-cache-dir azure-cli || \
    (sleep 5 && pip install --no-cache-dir azure-cli)

# Remove build dependencies to reduce image size
RUN apk del gcc musl-dev libffi-dev python3-dev || true

# Create non-root user for running the application
RUN addgroup -g 1000 certbot-user && \
    adduser -D -u 1000 -G certbot-user certbot-user

# Create mount point for secrets output
RUN mkdir -p /mnt/secrets-output && \
    chown certbot-user:certbot-user /mnt/secrets-output

# Create directory for certbot work
RUN mkdir -p /var/lib/letsencrypt && \
    mkdir -p /var/log/letsencrypt && \
    mkdir -p /etc/letsencrypt && \
    chown -R certbot-user:certbot-user /var/lib/letsencrypt /var/log/letsencrypt /etc/letsencrypt

# Copy the certificate management script
COPY --chown=certbot-user:certbot-user certbot-azure.sh /usr/local/bin/certbot-azure.sh
RUN chmod +x /usr/local/bin/certbot-azure.sh

# Switch to non-root user
USER certbot-user

# Set working directory
WORKDIR /home/certbot-user

# Default command runs the certificate management script
CMD ["/usr/local/bin/certbot-azure.sh"]
