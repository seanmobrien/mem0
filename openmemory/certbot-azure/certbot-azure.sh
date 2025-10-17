#!/bin/bash
set -e

# Certificate Management Script for Certbot with deSEC and Azure Key Vault
# Supports requesting and renewing Let's Encrypt certificates via DNS challenge

# ============================================================================
# Configuration - Accept parameters with fallback to environment variables
# ============================================================================

# Certificate configuration
DOMAIN="${1:-${CERTMGR_DOMAIN}}"
EMAIL="${2:-${CERTMGR_EMAIL}}"
DESEC_TOKEN="${3:-${CERTMGR_DESEC_TOKEN}}"

# Azure configuration
AZURE_TENANT_ID="${4:-${CERTMGR_AZURE_TENANT_ID}}"
AZURE_CLIENT_ID="${5:-${CERTMGR_AZURE_CLIENT_ID}}"
AZURE_CLIENT_SECRET="${6:-${CERTMGR_AZURE_CLIENT_SECRET}}"
AZURE_KEYVAULT_NAME="${7:-${CERTMGR_AZURE_KEYVAULT_NAME}}"
AZURE_CERT_NAME="${8:-${CERTMGR_AZURE_CERT_NAME}}"

# Optional configuration
RENEWAL_MODE="${9:-${CERTMGR_RENEWAL_MODE:-false}}"
STAGING="${10:-${CERTMGR_STAGING:-false}}"

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
    [ -z "$DESEC_TOKEN" ] && missing_params+=("DESEC_TOKEN")
    [ -z "$AZURE_TENANT_ID" ] && missing_params+=("AZURE_TENANT_ID")
    [ -z "$AZURE_CLIENT_ID" ] && missing_params+=("AZURE_CLIENT_ID")
    [ -z "$AZURE_CLIENT_SECRET" ] && missing_params+=("AZURE_CLIENT_SECRET")
    [ -z "$AZURE_KEYVAULT_NAME" ] && missing_params+=("AZURE_KEYVAULT_NAME")
    [ -z "$AZURE_CERT_NAME" ] && missing_params+=("AZURE_CERT_NAME")
    
    if [ ${#missing_params[@]} -gt 0 ]; then
        log_error "Missing required parameters: ${missing_params[*]}"
        log_error "Usage: $0 <domain> <email> <desec_token> <azure_tenant_id> <azure_client_id> <azure_client_secret> <azure_keyvault_name> <azure_cert_name> [renewal_mode] [staging]"
        log_error "Or set environment variables: CERTMGR_DOMAIN, CERTMGR_EMAIL, CERTMGR_DESEC_TOKEN, CERTMGR_AZURE_TENANT_ID, CERTMGR_AZURE_CLIENT_ID, CERTMGR_AZURE_CLIENT_SECRET, CERTMGR_AZURE_KEYVAULT_NAME, CERTMGR_AZURE_CERT_NAME"
        exit 1
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
        exit 1
    fi
    
    log_info "Output directory: /mnt/secrets-output"
}

# ============================================================================
# Main Certificate Request/Renewal Logic
# ============================================================================

request_certificate() {
    log_info "Starting certificate request for domain: $DOMAIN"
    
    # Create deSEC credentials file
    local desec_creds="/tmp/desec-credentials.ini"
    cat > "$desec_creds" <<EOF
dns_desec_token = $DESEC_TOKEN
dns_desec_endpoint = https://desec.io
EOF
    chmod 600 "$desec_creds"
    
    # Build certbot command
    local certbot_cmd="certbot certonly"
    certbot_cmd="$certbot_cmd --dns-desec"
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
        exit 1
    fi
    
    # Clean up credentials file
    rm -f "$desec_creds"
}

export_certificates() {
    log_info "Exporting certificates to /mnt/secrets-output"
    
    # Determine certificate path
    local cert_path="/etc/letsencrypt/live/$DOMAIN"
    
    if [ ! -d "$cert_path" ]; then
        log_error "Certificate directory not found: $cert_path"
        exit 1
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
        exit 1
    fi
    
    log_info "Uploading certificate to Azure Key Vault: $AZURE_KEYVAULT_NAME"
    
    # Create PFX file from certificate and private key
    local pfx_file="/tmp/certificate.pfx"
    local pfx_password=$(openssl rand -base64 32)
    
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
        exit 1
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
    log_info "=== Certbot Azure Certificate Manager ==="
    
    # Validate parameters
    validate_required_params
    
    # Setup output directory
    setup_output_directory
    
    # Request or renew certificate
    request_certificate
    
    # Export certificates
    export_certificates
    
    # Upload to Azure Key Vault
    upload_to_azure_keyvault
    
    log_success "=== Certificate management completed successfully ==="
    
    # Keep container alive if requested
    if [ "${CERTMGR_KEEPALIVE:-false}" = "true" ]; then
        log_info "CERTMGR_KEEPALIVE is set, launching bash shell..."
        exec /bin/bash
    fi
}

# Run main function
main
