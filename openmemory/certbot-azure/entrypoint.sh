#!/bin/sh
set -euo pipefail

# entrypoint.sh — runs as root, ensures mounts are writable, then drops to certbot-user

log() {
  printf '[entrypoint] %s\n' "$1"
}

# Ensure the output directory exists
mkdir -p /mnt/secrets-output

# If not writable, try to chown to certbot-user (uid 1000)
if [ ! -w /mnt/secrets-output ]; then
  log "/mnt/secrets-output not writable; attempting chown to certbot-user:certbot-user"
  chmod -R 700 /mnt/secrets-output 2>/dev/null || log "chmod failed or not permitted"
  chown -R certbot-user:certbot-user /mnt/secrets-output 2>/dev/null || log "chown failed or not permitted"
fi

# Prefer su-exec or gosu for dropping privileges; fall back to su -c if needed
if command -v su-exec >/dev/null 2>&1; then
  # run script under bash so bash-specific constructs (arrays, local -a) work
  exec su-exec certbot-user bash /usr/local/bin/certbot-azure.sh
elif command -v gosu >/dev/null 2>&1; then
  exec gosu certbot-user bash /usr/local/bin/certbot-azure.sh
else
  # Last resort: run the script directly; if the Dockerfile switched USER to certbot-user
  # the script will already run as non-root. Otherwise this runs as root.
  exec /bin/bash /usr/local/bin/certbot-azure.sh
fi
