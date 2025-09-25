#!/bin/bash
set -euo pipefail

echo "Setting up BOLT certificates..."

# Create certificates directory if it doesn't exist
CERT_DIR="/var/lib/neo4j/certificates/bolt"
mkdir -p "$CERT_DIR"

# Check if BOLT_CRT and BOLT_KEY environment variables are defined
if [[ -n "${BOLT_CRT:-}" && -n "${BOLT_KEY:-}" ]]; then
    echo "Found BOLT_CRT and BOLT_KEY environment variables, writing to certificate files..."
    
    # Write certificate from environment variable
    echo "$BOLT_CRT" > "$CERT_DIR/bolt.crt"
    echo "Certificate written to $CERT_DIR/bolt.crt"
    
    # Write private key from environment variable
    echo "$BOLT_KEY" > "$CERT_DIR/bolt.key"
    echo "Private key written to $CERT_DIR/bolt.key"
    
    # Set appropriate permissions
    chmod 644 "$CERT_DIR/bolt.crt"
    chmod 600 "$CERT_DIR/bolt.key"
    
else
    echo "BOLT_CRT and/or BOLT_KEY not found, generating self-signed certificate..."
    
    # Generate self-signed certificate and private key
    openssl req -x509 -newkey rsa:4096 -keyout "$CERT_DIR/bolt.key" -out "$CERT_DIR/bolt.crt" \
        -days 365 -nodes \
        -subj "/C=US/ST=State/L=City/O=Organization/OU=OrgUnit/CN=neo4j"
    
    echo "Self-signed certificate generated:"
    echo "  Certificate: $CERT_DIR/bolt.crt"
    echo "  Private key: $CERT_DIR/bolt.key"
    
    # Set appropriate permissions
    chmod 644 "$CERT_DIR/bolt.crt"
    chmod 600 "$CERT_DIR/bolt.key"
fi

# Change ownership to neo4j user if it exists
if id "neo4j" &>/dev/null; then
    chown -R neo4j:neo4j "$CERT_DIR"
    echo "Changed ownership of certificates to neo4j user"
fi

echo "BOLT certificate setup complete."
