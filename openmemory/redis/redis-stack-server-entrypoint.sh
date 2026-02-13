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
  printf '\033[31mMissing Redis password secret at %s\033[0m\n' "$SECRET_PATH" >&2
  exit 1
fi

PASSWORD=$(tr -d '\r\n' < "$SECRET_PATH")
if [ -z "$PASSWORD" ]; then
  printf '\033[31mRedis password secret is empty\033[0m\n' >&2
  exit 1
fi

# Best-effort host-level safety: try to enable overcommit if permitted.
if command -v sysctl >/dev/null 2>&1; then
  set +e
  if ! sysctl -w vm.overcommit_memory=1 >/dev/null 2>&1; then
    printf '\033[33mWarning: unable to set vm.overcommit_memory=1; continuing without change\033[0m\n' >&2
  fi
  set -eu
fi

# Prepare TLS materials
TLS_KEY_PASS=""
if [ -f "$TLS_SECRET_PW" ]; then
  TLS_KEY_PASS=$(tr -d '\r\n' < "$TLS_SECRET_PW")
fi

if [ -f "$TLS_SECRET" ]; then
  cp "$TLS_SECRET" "$TLS_KEY"
  chmod 600 "$TLS_KEY"

  if [ -n "$TLS_KEY_PASS" ]; then
    if echo "$TLS_KEY_PASS" | openssl x509 -in "$TLS_SECRET" -passin fd:0 -noout >/dev/null 2>&1; then
      echo "$TLS_KEY_PASS" | openssl x509 -in "$TLS_SECRET" -passin fd:0 -out "$TLS_CERT" >/dev/null 2>&1 || true
    fi

    if [ ! -s "$TLS_CERT" ]; then
      echo "$TLS_KEY_PASS" | openssl req -x509 -passin fd:0 -key "$TLS_KEY" -new -out "$TLS_CERT" -days 365 -subj "/CN=redis" >/dev/null 2>&1 || {
        printf '\033[31mFailed to extract or build certificate from provided key\033[0m\n' >&2; exit 1; }
    fi
  else
    if openssl x509 -in "$TLS_SECRET" -noout >/dev/null 2>&1; then
      openssl x509 -in "$TLS_SECRET" -out "$TLS_CERT" >/dev/null 2>&1 || true
    fi

    if [ ! -s "$TLS_CERT" ]; then
      openssl req -x509 -key "$TLS_KEY" -new -out "$TLS_CERT" -days 365 -subj "/CN=redis" >/dev/null 2>&1 || {
        printf '\033[31mFailed to extract or build certificate from provided key\033[0m\n' >&2; exit 1; }
    fi
  fi
else
  openssl req -x509 -nodes -newkey rsa:4096 -keyout "$TLS_KEY" -out "$TLS_CERT" -days 365 -subj "/CN=redis" >/dev/null 2>&1 || {
    printf '\033[31mFailed to generate self-signed certificate\033[0m\n' >&2; exit 1; }
fi

# If no CA bundle provided, default to the cert we just produced/extracted.
if [ ! -f "$TLS_CA" ] || [ ! -s "$TLS_CA" ]; then
  printf '\033[33mNo CA certificate provided; using server certificate as CA\033[0m\n' >&2
  TLS_CA="$TLS_CERT"
fi
TLS_PASS_ARG=""
[ -n "$TLS_KEY_PASS" ] && TLS_PASS_ARG="--tls-key-file-pass $TLS_KEY_PASS"

if getent passwd redis >/dev/null 2>&1; then
  chown -R redis:redis "$TLS_DIR" || true
fi

# REDIS_EXTRA_ARGS can be provided to append more flags if needed.
export REDIS_ARGS="--requirepass $PASSWORD --port $PORT --tls-port $TLS_PORT --tls-cert-file $TLS_CERT --tls-key-file $TLS_KEY --tls-ca-cert-file $TLS_CA --notify-keyspace-events Ex $TLS_PASS_ARG ${REDIS_EXTRA_ARGS:-}"

for ep in /usr/local/bin/docker-entrypoint.sh /entrypoint.sh; do
  if [ -x "$ep" ]; then
    exec "$ep" "$@"
  fi
done

printf '\033[31mNo upstream entrypoint found\033[0m\n' >&2
exit 127