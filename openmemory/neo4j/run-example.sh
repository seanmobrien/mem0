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
if [ -z "$PFX_PASS" ]; then
    echo "Error: PFX_PASS is not set"
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
    -e AZURE_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID" \
    -e AZURE_RESOURCE_GROUP="$AZURE_RESOURCE_GROUP" \
    -e KEY_VAULT_NAME="$KEY_VAULT_NAME" \
    -e KEY_NAME="$KEY_NAME" \
    -e PFX_PASS="$PFX_PASS" \
    -e TENANT_ID="$TENANT_ID" \
    openmemory-neo4j

echo "Certificate management completed!"
echo "Certificates are available in: $CERTS_DIR"
