#!/bin/sh

# Extract private/public key pair from combined PEM at /mnt/secrets/cert-https
PEM_SRC="/mnt/secrets/cert-https"
OUT_DIR="/opt/keycloak/conf"
PRIV_OUT="$OUT_DIR/server.key.pem"
CERT_OUT="$OUT_DIR/truststores/server.crt.pem"

if [ ! -s "$PEM_SRC" ]; then
    echo "PEM source file not found or empty: $PEM_SRC" >&2
    exit 1
fi

# Extract private key (supports RSA, EC, PKCS8)
awk 'BEGIN{p=0} /BEGIN .*PRIVATE KEY/{p=1} {if(p)print} /END .*PRIVATE KEY/{p=0}' "$PEM_SRC" > "$PRIV_OUT" || exit 1

# Extract first certificate (public key)
awk 'BEGIN{c=0} /BEGIN CERTIFICATE/{c=1} {if(c)print} /END CERTIFICATE/{if(c){exit}}' "$PEM_SRC" > "$CERT_OUT" || exit 1

# Validate extraction
if ! grep -q "BEGIN CERTIFICATE" "$CERT_OUT"; then
    echo "Failed to extract certificate" >&2
    exit 1
fi
if ! grep -q "PRIVATE KEY" "$PRIV_OUT"; then
    echo "Failed to extract private key" >&2
    exit 1
fi

chmod 600 "$PRIV_OUT"
chmod 644 "$CERT_OUT"
echo "Extracted private key to $PRIV_OUT and certificate to $CERT_OUT"
echo "------- Current configuration -------"
cd /opt/keycloak
./bin/kc.sh show-config
echo "------- Starting Keycloak -------"
./bin/kc.sh start --optimized
