FROM redis/redis-stack-server:latest

# Ensure openssl is available for TLS key/cert handling
RUN apt-get update \ 
  && apt-get install -y --no-install-recommends openssl \ 
  && rm -rf /var/lib/apt/lists/*

# Entrypoint to load password from a mounted secret and pass it via REDIS_ARGS.
# Falls back to the upstream entrypoint once REDIS_ARGS is set.
RUN set -eu; \
  cat <<'EOF' > /usr/local/bin/redis-stack-entrypoint.sh
#!/bin/sh
set -eu

SECRET_PATH="${REDIS_PASSWORD_FILE:-/run/secrets/REDIS_PW}"
PORT="${REDIS_PORT:-16379}"

TLS_PORT="${REDIS_TLS_PORT:-16380}"
TLS_DIR="${REDIS_TLS_DIR:-/data/tls}"
TLS_SECRET="${REDIS_CERT_FILE:-/run/secrets/REDIS_CERT}"
TLS_SECRET_PW="${REDIS_CERT_PW_FILE:-/run/secrets/REDIS_CERT_PW}"
TLS_KEY="$TLS_DIR/redis.key"
TLS_CERT="$TLS_DIR/redis.crt"
TLS_CA="$TLS_DIR/redis.ca.crt"

mkdir -p "$TLS_DIR"
if getent passwd redis >/dev/null 2>&1; then
  chown redis:redis "$TLS_DIR" || true
fi

if [ ! -f "$SECRET_PATH" ]; then
  echo "Missing Redis password secret at $SECRET_PATH" >&2
  exit 1
fi

PASSWORD=$(tr -d '\r\n' < "$SECRET_PATH")
if [ -z "$PASSWORD" ]; then
  echo "Redis password secret is empty" >&2
  exit 1
fi

# Best-effort host-level safety: try to enable overcommit if permitted.
if command -v sysctl >/dev/null 2>&1; then
  sysctl -w vm.overcommit_memory=1 >/dev/null 2>&1 || true
fi

# Prepare TLS materials
TLS_KEY_PASS=""
if [ -f "$TLS_SECRET_PW" ]; then
  TLS_KEY_PASS=$(tr -d '\r\n' < "$TLS_SECRET_PW")
fi

if [ -f "$TLS_SECRET" ]; then
  cp "$TLS_SECRET" "$TLS_KEY"
  chmod 600 "$TLS_KEY"

  PASSIN=""
  [ -n "$TLS_KEY_PASS" ] && PASSIN="-passin pass:$TLS_KEY_PASS"

  if openssl x509 -in "$TLS_SECRET" $PASSIN -noout >/dev/null 2>&1; then
    openssl x509 -in "$TLS_SECRET" $PASSIN -out "$TLS_CERT" >/dev/null 2>&1 || true
  fi

  if [ ! -s "$TLS_CERT" ]; then
    openssl req -x509 $PASSIN -key "$TLS_KEY" -new -out "$TLS_CERT" -days 365 -subj "/CN=redis" >/dev/null 2>&1 || {
      echo "Failed to extract or build certificate from provided key" >&2; exit 1; }
  fi

else
  openssl req -x509 -nodes -newkey rsa:4096 -keyout "$TLS_KEY" -out "$TLS_CERT" -days 365 -subj "/CN=redis" >/dev/null 2>&1 || {
    echo "Failed to generate self-signed certificate" >&2; exit 1; }
fi

# If no CA bundle provided, default to the cert we just produced/extracted.
if [ ! -f "$TLS_CA" ] || [ ! -s "$TLS_CA" ]; then
  TLS_CA="$TLS_CERT"
fi
TLS_PASS_ARG=""
[ -n "$TLS_KEY_PASS" ] && TLS_PASS_ARG="--tls-key-file-pass $TLS_KEY_PASS"

if getent passwd redis >/dev/null 2>&1; then
  chown -R redis:redis "$TLS_DIR" || true
fi

# REDIS_EXTRA_ARGS can be provided to append more flags if needed.
export REDIS_ARGS="--requirepass $PASSWORD --port $PORT --tls-port $TLS_PORT --tls-cert-file $TLS_CERT --tls-key-file $TLS_KEY --tls-ca-cert-file $TLS_CA $TLS_PASS_ARG ${REDIS_EXTRA_ARGS:-}"

for ep in /usr/local/bin/docker-entrypoint.sh /entrypoint.sh /usr/local/bin/redis-stack-server-entrypoint.sh; do
  if [ -x "$ep" ]; then
    exec "$ep" "$@"
  fi
done

echo "No upstream entrypoint found" >&2
exit 127
EOF

RUN chmod +x /usr/local/bin/redis-stack-entrypoint.sh

EXPOSE 16379

ENTRYPOINT ["/usr/local/bin/redis-stack-entrypoint.sh"]
CMD ["redis-server"]
