#!/usr/bin/env bash
set -euo pipefail

ENV_EXACT_NAME="ComplianceTheatre2000"
CONTAINER_NAME="mem0-api"
OUT_FILE="mem0-api-env-backup-$(date +%Y%m%d-%H%M%S).json"

command -v az >/dev/null || { echo "az CLI is required"; exit 1; }
command -v jq >/dev/null || { echo "jq is required"; exit 1; }

tmp_apps="$(mktemp)"
trap 'rm -f "$tmp_apps"' EXIT

echo "Discovering Container App Environment named ${ENV_EXACT_NAME} across subscriptions..."

found_any=0
while IFS= read -r sub_id; do
  az account set --subscription "$sub_id" >/dev/null

  az containerapp env list \
    --query "[?name=='${ENV_EXACT_NAME}'].{subscriptionId:'${sub_id}',resourceGroup:resourceGroup,name:name,id:id}" \
    -o json >> "$tmp_apps"

  if [[ "$(tail -n 1 "$tmp_apps")" != "[]" ]]; then
    found_any=1
  fi
done < <(az account list --query "[].id" -o tsv)

if [[ "$found_any" -eq 0 ]]; then
  echo "No Container App Environment named ${ENV_EXACT_NAME} was found in accessible subscriptions."
  exit 1
fi

app_matches="$(jq -s 'add' "$tmp_apps")"
match_count="$(echo "$app_matches" | jq 'length')"

if [[ "$match_count" -gt 1 ]]; then
  echo "Multiple environments named ${ENV_EXACT_NAME} found. Narrow this script or pick one manually:"
  echo "$app_matches" | jq
  exit 1
fi

SUB_ID="$(echo "$app_matches" | jq -r '.[0].subscriptionId')"
RG="$(echo "$app_matches" | jq -r '.[0].resourceGroup')"
ENV_NAME="$(echo "$app_matches" | jq -r '.[0].name')"

echo "Discovered environment:"
echo "  subscription: ${SUB_ID}"
echo "  resourceGroup: ${RG}"
echo "  environment: ${ENV_NAME}"

az account set --subscription "$SUB_ID" >/dev/null

# Find container apps that belong to this managed environment
candidate_apps_json="$(az containerapp list \
  --resource-group "$RG" \
  --query "[?contains(properties.managedEnvironmentId, '/managedEnvironments/${ENV_NAME}')].{name:name,containers:properties.template.containers}" \
  -o json)"

APP_NAME="$(echo "$candidate_apps_json" | jq -r --arg c "$CONTAINER_NAME" '.[] | select((.containers // []) | any(.name == $c)) | .name' | head -n 1)"

if [[ -z "$APP_NAME" ]]; then
  echo "No container app in environment ${ENV_NAME} contains container ${CONTAINER_NAME}."
  echo "Container apps discovered in environment:"
  echo "$candidate_apps_json" | jq -r '.[].name'
  exit 1
fi

echo "Discovered container app: ${APP_NAME}"

container_json="$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --query "properties.template.containers[?name=='${CONTAINER_NAME}'] | [0]" \
  -o json)"

if [[ "$container_json" == "null" ]]; then
  echo "Container ${CONTAINER_NAME} not found in app ${APP_NAME}."
  echo "Available containers:"
  az containerapp show --name "$APP_NAME" --resource-group "$RG" \
    --query "properties.template.containers[].name" -o tsv
  exit 1
fi

# Secret values may be masked or unavailable depending on RBAC/policy.
secrets_json="$(az containerapp secret list --name "$APP_NAME" --resource-group "$RG" -o json 2>/dev/null || echo '[]')"

jq -n \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg subscriptionId "$SUB_ID" \
  --arg resourceGroup "$RG" \
  --arg containerApp "$APP_NAME" \
  --arg containerName "$CONTAINER_NAME" \
  --argjson container "$container_json" \
  --argjson secrets "$secrets_json" '
{
  generatedAt: $generatedAt,
  subscriptionId: $subscriptionId,
  resourceGroup: $resourceGroup,
  containerApp: $containerApp,
  containerName: $containerName,
  image: ($container.image // null),

  envCurrent: (
    ($container.env // [])
    | map(
        . as $e
        | if ($e.value? != null) then
            { name: $e.name, type: "value", value: $e.value }
          elif ($e.secretRef? != null) then
            {
              name: $e.name,
              type: "secretRef",
              secretRef: $e.secretRef,
              secretValueIfReadable: (
                ($secrets[]? | select(.name == $e.secretRef) | .value) // null
              )
            }
          else
            { name: $e.name, type: "unknown" }
          end
      )
  ),

  restorePayload: (
    ($container.env // [])
    | map(
        if (.value? != null) then
          { name: .name, value: .value }
        elif (.secretRef? != null) then
          { name: .name, secretRef: .secretRef }
        else
          { name: .name }
        end
      )
  )
}' | tee "$OUT_FILE"

echo
echo "Backup JSON written to: $OUT_FILE"

