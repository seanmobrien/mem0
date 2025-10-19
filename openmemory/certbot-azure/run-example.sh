#!/bin/bash
# Example usage script for certbot-azure
# This demonstrates how to run the container with environment variables

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    . .env
    set +a
fi

# Check if required environment variables are set
if [ -z "$CERTMGR_DOMAIN" ]; then
    echo "Error: CERTMGR_DOMAIN is not set"
    echo "Please create a .env file from .env.example and fill in your values"
    exit 1
fi

# Create a directory for certificates if it doesn't exist
CERTS_DIR="${CERTS_DIR:-./certs}"
mkdir -p "$CERTS_DIR"

echo "Starting certbot-azure container..."

# Run the container
docker run --rm \
    -it \
    -v "$CERTS_DIR:/mnt/secrets-output" \
    -e CERTMGR_DOMAIN="$CERTMGR_DOMAIN" \
    -e CERTMGR_EMAIL="$CERTMGR_EMAIL" \
    -e CERTMGR_DESEC_TOKEN="$CERTMGR_DESEC_TOKEN" \
    -e CERTMGR_CLOUDFLARE_EMAIL="$CERTMGR_CLOUDFLARE_EMAIL" \
    -e CERTMGR_CLOUDFLARE_TOKEN="$CERTMGR_CLOUDFLARE_TOKEN" \
    -e CERTMGR_DNS_PROVIDER="${CERTMGR_DNS_PROVIDER:-auto}" \
    -e CERTMGR_AZURE_TENANT_ID="$CERTMGR_AZURE_TENANT_ID" \
    -e CERTMGR_AZURE_CLIENT_ID="$CERTMGR_AZURE_CLIENT_ID" \
    -e CERTMGR_AZURE_CLIENT_SECRET="$CERTMGR_AZURE_CLIENT_SECRET" \
    -e CERTMGR_AZURE_KEYVAULT_NAME="$CERTMGR_AZURE_KEYVAULT_NAME" \
    -e CERTMGR_AZURE_CERT_NAME="$CERTMGR_AZURE_CERT_NAME" \
    -e CERTMGR_RENEWAL_MODE="${CERTMGR_RENEWAL_MODE:-false}" \
    -e CERTMGR_STAGING="${CERTMGR_STAGING:-false}" \
    -e CERTMGR_KEEPALIVE="${CERTMGR_KEEPALIVE:-false}" \
    openmemory/certbot-azure

echo "Certificate management completed!"
echo "Certificates are available in: $CERTS_DIR"
