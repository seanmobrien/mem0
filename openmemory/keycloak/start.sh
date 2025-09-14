#!/bin/sh

if [ "$1" = "debug" ]; then
    KEEPALIVE_INTERVAL=10
    echo "Debug keep-alive mode. Press any key (or Ctrl+C) to exit."
    while :; do
        echo keep-alive
        # Wait up to ${KEEPALIVE_INTERVAL}s for a single keypress; if received, exit loop
        if ( read -r -t "$KEEPALIVE_INTERVAL" _key ) 2>/dev/null; then
            echo "Key pressed, exiting debug mode."
            break
        fi
        sleep "$KEEPALIVE_INTERVAL"
    done
fi


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
sed -n '/BEGIN .*PRIVATE KEY/,/END .*PRIVATE KEY/p' "$PEM_SRC" > "$PRIV_OUT" || exit 1

# Extract first certificate (public key)
sed -n '/BEGIN CERTIFICATE/,/END CERTIFICATE/{
    p
    /END CERTIFICATE/q
}' "$PEM_SRC" > "$CERT_OUT" || exit 1

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
exec /opt/keycloak/bin/kc.sh start --optimized
