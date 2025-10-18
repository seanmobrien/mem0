#!/bin/bash
set -euo pipefail

run_keepalive() {
  set -euo pipefail
  trap 'echo "SIGTERM received, exiting"; exit 0' TERM INT
  echo "Startup tasks completed; entering keepalive - press Ctrl-X to exit"
# Read from the TTY so Ctrl+X can be detected even when stdin is redirected
while true; do    
    # wait up to 15s for a single keypress; -s silent, -n1 one char, -t timeout
    if read -rsn1 -t 15 key < /dev/tty; then
        # Ctrl-X is ASCII 0x18
        if [[ $key == $'\x18' ]]; then
            echo "Ctrl-X received, exiting"
            break
        fi
    fi
done
}

error_exit() {    
  log_error "=== Certificate management failed ==="
  # Keep container alive if requested
  if [ "${CERTMGR_KEEPALIVE:-false}" = "true" ]; then
    run_keepalive
  fi  
  exit 1
}

on_error() {
  local exit_code=$?
  echo "ERROR: command failed at line $1 (exit $exit_code): $BASH_COMMAND"
  error_exit
}
trap 'on_error $LINENO' ERR

# Certificate Management Script for Certbot with deSEC and Azure Key Vault
# Supports requesting and renewing Let's Encrypt certificates via DNS challenge
# Automatically detects DNS provider (deSEC or Cloudflare) based on nameservers

# ============================================================================
# Configuration - Accept parameters with fallback to environment variables
# ============================================================================

# Certificate configuration
DOMAIN="${1:-${CERTMGR_DOMAIN}}"
EMAIL="${2:-${CERTMGR_EMAIL}}"
DESEC_TOKEN="${3:-${CERTMGR_DESEC_TOKEN}}"
CERTMGR_CLOUDFLARE_TOKEN="${CERTMGR_CLOUDFLARE_TOKEN}"

# Azure configuration  
AZURE_TENANT_ID="${4:-${CERTMGR_AZURE_TENANT_ID}}"
AZURE_CLIENT_ID="${5:-${CERTMGR_AZURE_CLIENT_ID}}"
AZURE_CLIENT_SECRET="${6:-${CERTMGR_AZURE_CLIENT_SECRET}}"
AZURE_KEYVAULT_NAME="${7:-${CERTMGR_AZURE_KEYVAULT_NAME}}"
AZURE_CERT_NAME="${8:-${CERTMGR_AZURE_CERT_NAME}}"

# Optional configuration
RENEWAL_MODE="${9:-${CERTMGR_RENEWAL_MODE:-false}}"
STAGING="${10:-${CERTMGR_STAGING:-false}}"

echo "=== Certbot Azure Certificate Manager configuration ==="
echo "Domain: $CERTMGR_DOMAIN"
echo "Email: $EMAIL"
echo "deSEC Token: [Secret Hidden]"
echo "Azure Tenant ID: $AZURE_TENANT_ID"
echo "Azure Client ID: $AZURE_CLIENT_ID"
echo "Azure Client Secret: [Secret Hidden]"
echo "Key Vault: $AZURE_KEYVAULT_NAME"
echo "Certificate Name: $AZURE_CERT_NAME"
echo "Renewal Mode: $RENEWAL_MODE"
echo "Staging: $STAGING"
echo "Keepalive: ${CERTMGR_KEEPALIVE:-false}"

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo "[SUCCESS] $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

validate_required_params() {
    local missing_params=()
    [ -z "$DOMAIN" ] && missing_params+=("DOMAIN")
    [ -z "$EMAIL" ] && missing_params+=("EMAIL")
    [ -z "$AZURE_TENANT_ID" ] && missing_params+=("AZURE_TENANT_ID")
    [ -z "$AZURE_CLIENT_ID" ] && missing_params+=("AZURE_CLIENT_ID")
    [ -z "$AZURE_CLIENT_SECRET" ] && missing_params+=("AZURE_CLIENT_SECRET")
    [ -z "$AZURE_KEYVAULT_NAME" ] && missing_params+=("AZURE_KEYVAULT_NAME")
    [ -z "$AZURE_CERT_NAME" ] && missing_params+=("AZURE_CERT_NAME")

    if [ ${#missing_params[@]} -gt 0 ]; then
        log_error "Missing required parameters: ${missing_params[*]}"
        log_error "Usage: $0 <domain> <email> <desec_token> <azure_tenant_id> <azure_client_id> <azure_client_secret> <azure_keyvault_name> <azure_cert_name> [renewal_mode] [staging]"
        log_error "Or set environment variables: CERTMGR_DOMAIN, CERTMGR_EMAIL, CERTMGR_DESEC_TOKEN, CERTMGR_AZURE_TENANT_ID, CERTMGR_AZURE_CLIENT_ID, CERTMGR_AZURE_CLIENT_SECRET, CERTMGR_AZURE_KEYVAULT_NAME, CERTMGR_AZURE_CERT_NAME"
        error_exit
    fi
}

setup_output_directory() {
    # Ensure /mnt/secrets-output exists, create ephemeral mount if needed
    if [ ! -d "/mnt/secrets-output" ]; then
        log_info "Creating ephemeral mount at /mnt/secrets-output"
        mkdir -p /mnt/secrets-output
    fi
    
    # Check if we can write to the directory
    if [ ! -w "/mnt/secrets-output" ]; then
        log_error "/mnt/secrets-output is not writable"
        error_exit
    fi
    
    log_info "Output directory: /mnt/secrets-output"
}

detect_dns_provider() {
    log_info "Detecting DNS provider for domain: $DOMAIN"
    
    # If provider is explicitly set, use it
    if [ "$DNS_PROVIDER" != "auto" ]; then
        log_info "DNS provider explicitly set to: $DNS_PROVIDER"
        return 0
    fi
    
    # Extract the base domain (handle wildcards and subdomains)
    local check_domain="$DOMAIN"
    if [[ "$check_domain" == \** ]]; then
        check_domain="${check_domain#\*.}"
    fi
    
    log_info "Checking nameservers for domain: $check_domain"
    
    # Try to detect provider by querying nameservers
    local current_domain="$check_domain"
    local max_attempts=10
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        log_info "Querying nameservers for: $current_domain"
        
        # Query nameservers for the current domain
        local nameservers
        nameservers=$(dig +short NS "$current_domain" 2>/dev/null | grep -v '^$' || true)
        
        if [ -n "$nameservers" ]; then
            log_info "Found nameservers for $current_domain:"
            echo "$nameservers" | while read -r ns; do
                log_info "  - $ns"
            done
            
            # Check for deSEC nameservers
            if echo "$nameservers" | grep -qi "desec."; then
                DNS_PROVIDER="desec"
                log_success "Detected deSEC as DNS provider"
                return 0
            fi
            
            # Check for Cloudflare nameservers
            if echo "$nameservers" | grep -qi "cloudflare."; then
                DNS_PROVIDER="cloudflare"
                log_success "Detected Cloudflare as DNS provider"
                return 0
            fi
            
            log_info "Nameservers found but provider not recognized"
        else
            log_info "No nameservers found for $current_domain"
        fi
        
        # Move to parent domain
        if [[ "$current_domain" == *.* ]]; then
            current_domain="${current_domain#*.}"
            log_info "Moving to parent domain: $current_domain"
        else
            log_error "Reached top-level domain without finding supported nameservers"
            break
        fi
        
        attempt=$((attempt + 1))
    done
    
    log_error "Unable to detect DNS provider automatically"
    log_error "Supported providers: deSEC (*.desec.io, *.desec.org nameservers), Cloudflare (*.cloudflare.com nameservers)"
    log_error "Please set CERTMGR_DNS_PROVIDER explicitly to 'desec' or 'cloudflare'"
    error_exit
}

validate_provider_credentials() {
    log_info "Validating credentials for DNS provider: $DNS_PROVIDER"
    
    case "$DNS_PROVIDER" in
        desec)
            if [ -z "$DESEC_TOKEN" ]; then
                log_error "deSEC provider selected but CERTMGR_DESEC_TOKEN is not set"
                error_exit
            fi
            log_success "deSEC credentials validated"
            ;;
        cloudflare)
            if [ -z "$CLOUDFLARE_TOKEN" ]; then
                log_error "Cloudflare provider selected but CERTMGR_CLOUDFLARE_TOKEN is not set"
                error_exit
            fi
            log_success "Cloudflare credentials validated"
            ;;
        *)
            log_error "Unknown DNS provider: $DNS_PROVIDER"
            error_exit
            ;;
    esac
}

# ============================================================================
# Main Certificate Request/Renewal Logic
# ============================================================================

request_certificate() {
    log_info "Starting certificate request for domain: $DOMAIN"    
    # Create deSEC credentials file
    mkdir -p "/etc/letsencrypt/$DOMAIN"
    local desec_creds="/etc/letsencrypt/$DOMAIN/desec-credentials.ini"
    cat > "$desec_creds" <<EOF
dns_desec_token = $DESEC_TOKEN
EOF
    chmod 600 "$desec_creds"
    
    # Build certbot command
    local certbot_cmd="certbot certonly -v"
    certbot_cmd="$certbot_cmd --authenticator dns-desec"
    certbot_cmd="$certbot_cmd --dns-desec-credentials $desec_creds"
    certbot_cmd="$certbot_cmd --dns-desec-propagation-seconds 60"
    certbot_cmd="$certbot_cmd --non-interactive"
    certbot_cmd="$certbot_cmd --agree-tos"
    certbot_cmd="$certbot_cmd --email $EMAIL"
    certbot_cmd="$certbot_cmd --domain $DOMAIN"
    
    # Add staging flag if requested
    if [ "$STAGING" = "true" ]; then
        log_info "Using Let's Encrypt staging environment"
        certbot_cmd="$certbot_cmd --staging"
    fi
    
    # Add force renewal flag if in renewal mode
    if [ "$RENEWAL_MODE" = "true" ]; then
        log_info "Running in renewal mode"
        certbot_cmd="$certbot_cmd --force-renewal"
    fi
    
    # Execute certbot
    log_info "Executing certbot command..."
    if eval "$certbot_cmd"; then
        log_success "Certificate obtained successfully"
    else
        log_error "Failed to obtain certificate"
        rm -f "$desec_creds"
        error_exit
    fi
    
    # Clean up credentials file
    [ -n "$creds_file" ] && rm -f "$creds_file"
}

export_certificates() {
    log_info "Exporting certificates to /mnt/secrets-output"
    
    # Determine certificate path
    local cert_path="/live/$DOMAIN"
    
    if [ ! -d "$cert_path" ]; then
        log_error "Certificate directory not found: $cert_path"
        error_exit
    fi
    
    # Copy certificates to output directory
    cp "$cert_path/fullchain.pem" "/mnt/secrets-output/fullchain.pem"
    cp "$cert_path/privkey.pem" "/mnt/secrets-output/privkey.pem"
    cp "$cert_path/cert.pem" "/mnt/secrets-output/cert.pem"
    cp "$cert_path/chain.pem" "/mnt/secrets-output/chain.pem"
    
    # Set permissions
    chmod 644 /mnt/secrets-output/fullchain.pem
    chmod 644 /mnt/secrets-output/cert.pem
    chmod 644 /mnt/secrets-output/chain.pem
    chmod 600 /mnt/secrets-output/privkey.pem
    
    log_success "Certificates exported to /mnt/secrets-output"
}

upload_to_azure_keyvault() {
    log_info "Authenticating with Azure..."
    
    # Login to Azure using service principal
    if az login --service-principal \
        --username "$AZURE_CLIENT_ID" \
        --password "$AZURE_CLIENT_SECRET" \
        --tenant "$AZURE_TENANT_ID" > /dev/null 2>&1; then
        log_success "Azure authentication successful"
    else
        log_error "Azure authentication failed"
        error_exit
    fi
    
    log_info "Uploading certificate to Azure Key Vault: $AZURE_KEYVAULT_NAME"
    
    # Create PFX file from certificate and private key
    local pfx_file="/etc/letsencrypt/$DOMAIN/certificate.pfx"
    local pfx_password
    pfx_password=$(openssl rand -base64 32)
    
    # Convert to PFX format
    openssl pkcs12 -export \
        -out "$pfx_file" \
        -inkey /mnt/secrets-output/privkey.pem \
        -in /mnt/secrets-output/fullchain.pem \
        -passout pass:"$pfx_password"
    
    # Upload to Azure Key Vault
    if az keyvault certificate import \
        --vault-name "$AZURE_KEYVAULT_NAME" \
        --name "$AZURE_CERT_NAME" \
        --file "$pfx_file" \
        --password "$pfx_password" > /dev/null 2>&1; then
        log_success "Certificate uploaded to Azure Key Vault: $AZURE_CERT_NAME"
    else
        log_error "Failed to upload certificate to Azure Key Vault"
        rm -f "$pfx_file"
        error_exit
    fi
    
    # Clean up
    rm -f "$pfx_file"
    
    # Logout from Azure
    az logout > /dev/null 2>&1
    log_info "Azure logout successful"
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    log_info "=== Starting ==="
    
    # Validate parameters
    validate_required_params
    
    # Setup output directory
    setup_output_directory
    
    # Detect and validate DNS provider
    detect_dns_provider
    validate_provider_credentials
    
    # Request or renew certificate
    request_certificate
    
    # Export certificates
    export_certificates
    
    # Upload to Azure Key Vault
    upload_to_azure_keyvault
    
    log_success "=== Certificate management completed successfully ==="
    
    # Keep container alive if requested
    if [ "${CERTMGR_KEEPALIVE:-false}" = "true" ]; then
        run_keepalive
    fi
}

# Run main function
main
