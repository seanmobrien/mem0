#!/usr/bin/env bash
set -euo pipefail

# Rotates an Azure Container Registry (ACR) token's credentials and updates GitHub secrets
# Requirements:
# - Azure CLI (az) logged in with rights to ACR and AAD
# - GitHub CLI (gh) authenticated with repo:admin scope OR GITHUB_TOKEN with secrets:write via REST
# - jq for JSON parsing
#
# Behavior:
# - Assumes the scope map and token already exist
# - Optionally recreates the token (delete + create) if --recreate is passed
# - Always regenerates credentials (password) and updates GitHub repo secrets ACR_USERNAME/ACR_PASSWORD
#
# Usage:
#   ./local-tools/generate-token.sh \
#     --registry schoollawregistry \
#     --token-name mem0-ci-token \
#     --repo-owner seanmobrien \
#     --repo-name mem0 \
#     [--recreate] [--scope-map mem0-builders] [--expiration-days 180]

REGISTRY=""
TOKEN_NAME=""
REPO_OWNER=""
REPO_NAME=""
SCOPE_MAP=""
RECREATE=false
EXPIRATION_DAYS=180

while [[ $# -gt 0 ]]; do
  case "$1" in
    --registry)
      REGISTRY="$2"; shift 2;;
    --token-name)
      TOKEN_NAME="$2"; shift 2;;
    --repo-owner)
      REPO_OWNER="$2"; shift 2;;
    --repo-name)
      REPO_NAME="$2"; shift 2;;
    --scope-map)
      SCOPE_MAP="$2"; shift 2;;
    --recreate)
      RECREATE=true; shift 1;;
    --expiration-days)
      EXPIRATION_DAYS="$2"; shift 2;;
    -h|--help)
      sed -n '1,80p' "$0"; exit 0;;
    *)
      echo "Unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ -z "$REGISTRY" || -z "$TOKEN_NAME" || -z "$REPO_OWNER" || -z "$REPO_NAME" ]]; then
  echo "Missing required args. See --help." >&2
  exit 2
fi

command -v az >/dev/null || { echo "az CLI required" >&2; exit 2; }
command -v gh >/dev/null || { echo "gh CLI required" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq required" >&2; exit 2; }

acr_login_server=$(az acr show -n "$REGISTRY" --query loginServer -o tsv)

if $RECREATE; then
  if [[ -z "$SCOPE_MAP" ]]; then
    echo "--recreate requires --scope-map to rebind the token" >&2
    exit 2
  fi
  echo "Deleting existing token $TOKEN_NAME (if exists)..."
  az acr token delete -n "$TOKEN_NAME" -r "$REGISTRY" --yes || true
  echo "Recreating token $TOKEN_NAME bound to scope map $SCOPE_MAP..."
  az acr token create -n "$TOKEN_NAME" -r "$REGISTRY" --scope-map "$SCOPE_MAP" >/dev/null
fi

echo "Generating credentials for token $TOKEN_NAME..."
creds_json=$(az acr token credential generate -n "$TOKEN_NAME" -r "$REGISTRY" --expiration-in-days "$EXPIRATION_DAYS" -o json)
username=$(echo "$creds_json" | jq -r .username)
password=$(echo "$creds_json" | jq -r .passwords[0].value)

if [[ -z "$username" || -z "$password" || "$username" == "null" || "$password" == "null" ]]; then
  echo "Failed to get token credentials" >&2
  exit 1
fi

echo "Updating GitHub secrets ACR_USERNAME / ACR_PASSWORD for $REPO_OWNER/$REPO_NAME ..."
# Requires gh auth with repo admin or repo scope
GH_REPO="$REPO_OWNER/$REPO_NAME"

echo -n "$username" | gh secret set ACR_USERNAME --repo "$GH_REPO" --body "$username"
# Mask the password via stdin
echo -n "$password" | gh secret set ACR_PASSWORD --repo "$GH_REPO" --body "$password"

echo "Done. Test login (optional): docker login $acr_login_server --username $username --password-stdin <<< '***'"
