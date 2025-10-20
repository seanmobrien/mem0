#!/bin/bash
set -euo pipefail

echo "Setting up BOLT certificates..."
# Create certificates directory if it doesn't exist
CERT_DIR="/var/lib/neo4j/certificates/bolt"
mkdir -p "$CERT_DIR"

# Check if BOLT_CRT and BOLT_KEY environment variables are defined
if [[ -n "${PFX_PASS:-}" && -n "${KEY_NAME:-}" ]]; then
    echo "Found KeyVault environment variables, downloading certificate..."

# Log into azure using the system-assigned managed identity
    az login --identity

    KEY_VAULT_SCOPE="/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP}/providers/Microsoft.KeyVault/vaults/${KEY_VAULT_NAME}/certificates/${KEY_NAME}"
    echo "Acquiring access token for Key Vault scope: $KEY_VAULT_SCOPE"
    TOKEN=$(az account get-access-token --scope "$KEY_VAULT_SCOPE" --query accessToken --output tsv) # > /dev/null 2>&1;
    # Download and extract certificate from Azure Key Vault
    CERT="$CERT_DIR/bolt"
    az keyvault secret download --vault-name "${KEY_VAULT_NAME}" --name "${KEY_NAME}" --file "$CERT.pfx" # > /dev/null 2>&1;
    echo "Certificate succesfully downloaded - extracting..."
    openssl pkcs12 -in "$CERT.pfx" -nocerts -nodes -passin pass:"${PFX_PASS}" -out "$CERT.key" \
        & openssl pkcs12 -in "$CERT.pfx" -clcerts -nokeys -passin pass:"${PFX_PASS}" -out "$CERT.crt" # > /dev/null 2>&1;
    
    # Set appropriate permissions
    chmod 644 "$CERT_DIR/bolt.crt"
    chmod 600 "$CERT_DIR/bolt.key"
    
fi

if [[ -n "${BOLT_CRT:-}" && -n "${BOLT_KEY:-}" && -f "${BOLT_CRT}" && -f "${BOLT_KEY}" ]]; then
    echo "✅ Successfully extracted bolt certificate from $VAULT/$KEY_NAME"
else
    echo "BOLT_CRT and/or BOLT_KEY not found, generating self-signed certificate..."
    
    # Generate self-signed certificate and private key
    openssl req -x509 -newkey rsa:4096 -keyout "$CERT_DIR/bolt.key" -out "$CERT_DIR/bolt.crt" \
        -days 365 -nodes \
        -subj "/C=US/ST=State/L=City/O=Organization/OU=OrgUnit/CN=neo4j"
    
    echo "Self-signed certificate generated:"
    echo "  Certificate: $CERT_DIR/bolt.crt"
    echo "  Private key: $CERT_DIR/bolt.key"    
fi

# Set appropriate permissions
chmod 644 "$CERT_DIR/bolt.crt"
chmod 600 "$CERT_DIR/bolt.key"

# Change ownership to neo4j user if it exists
if id "neo4j" &>/dev/null; then
    chown -R neo4j:neo4j "$CERT_DIR"
    echo "Changed ownership of certificates to neo4j user"
fi

echo "BOLT certificate setup complete."
