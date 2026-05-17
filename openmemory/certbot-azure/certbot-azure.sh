#!/bin/bash
set -euo pipefail

run_keepalive() {
  set -euo pipefail
  trap 'echo "SIGTERM received, exiting"; exit 0' TERM INT
  # timeout in seconds; default to 3600 (1 hour) unless overridden
  CERTMGR_KEEPALIVE_TIMEOUT=${CERTMGR_KEEPALIVE_TIMEOUT:-3600}
  log_info "Startup tasks completed; entering keepalive (timeout=${CERTMGR_KEEPALIVE_TIMEOUT}s) - press Ctrl-X to exit"

  local start_ts now elapsed
  # use SECONDS bash builtin for portable elapsed timing
  start_ts=$SECONDS

  # Read from the TTY so Ctrl-X can be detected even when stdin is redirected
  while true; do
    # Check timeout
    now=$SECONDS
    elapsed=$(( now - start_ts ))
    if [ "$elapsed" -ge "$CERTMGR_KEEPALIVE_TIMEOUT" ]; then
      log_info "Keepalive timeout reached (${elapsed}s >= ${CERTMGR_KEEPALIVE_TIMEOUT}s); exiting"
      break
    fi

    # Determine TTY availability once by trying to open /dev/tty for reading into fd 3
    if [ -z "${_KEEPALIVE_TTY_CHECKED:-}" ]; then
        if exec 3</dev/tty 2>/dev/null; then
            KEEPALIVE_HAS_TTY=1
            KEEPALIVE_TTY_FD=3
            log_info "TTY detected and accessible; waiting for Ctrl-X"
        else
            KEEPALIVE_HAS_TTY=0
            KEEPALIVE_TTY_FD=""
            log_info "No usable TTY detected; falling back to sleep-only keepalive"
        fi
        _KEEPALIVE_TTY_CHECKED=1
    fi

    if [ "${KEEPALIVE_HAS_TTY:-0}" -eq 1 ]; then
        # wait up to 15s for a single keypress; -s silent, -n1 one char, -t timeout
        # but never wait beyond the keepalive timeout remaining
        remaining=$(( CERTMGR_KEEPALIVE_TIMEOUT - elapsed ))
        if [ "$remaining" -le 0 ]; then
            # timeout reached in the middle of loop
            continue
        fi
        if [ "$remaining" -lt 15 ]; then
            rt="$remaining"
        else
            rt=15
        fi
        # read from the already-opened fd using bash's -u flag to avoid opening /dev/tty
        if read -u "$KEEPALIVE_TTY_FD" -rsn1 -t "$rt" key 2>/dev/null; then
            # Ctrl-X is ASCII 0x18
            if [[ $key == $'\\x18' ]]; then
                echo "Ctrl-X received, exiting"
                # close fd before exit
                exec {KEEPALIVE_TTY_FD}<&- 2>/dev/null || true
                break
            fi
        fi
    else
        # No TTY: sleep in short increments so signals are handled promptly
        sleep 15
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
DOMAIN="${CERTMGR_DOMAIN:-}"
EMAIL="${CERTMGR_EMAIL:-}"
DESEC_TOKEN="${CERTMGR_DESEC_TOKEN:-}"
CLOUDFLARE_EMAIL="${CERTMGR_CLOUDFLARE_EMAIL:-}"
CLOUDFLARE_TOKEN="${CERTMGR_CLOUDFLARE_TOKEN:-}"

# Azure configuration
AZURE_TENANT_ID="${CERTMGR_AZURE_TENANT_ID:-}"
AZURE_CLIENT_ID="${CERTMGR_AZURE_CLIENT_ID:-}"
AZURE_CLIENT_SECRET="${CERTMGR_AZURE_CLIENT_SECRET:-}"
AZURE_KEYVAULT_NAME="${CERTMGR_AZURE_KEYVAULT_NAME:-}"
AZURE_CERT_NAME="${CERTMGR_AZURE_CERT_NAME:-}"

# Optional configuration
RENEWAL_MODE="${CERTMGR_RENEWAL_MODE:-false}"
STAGING="${CERTMGR_STAGING:-false}"
DNS_PROVIDER="${CERTMGR_DNS_PROVIDER:-auto}"
RAW_STAGE="${CERTMGR_STAGE:-}"

usage() {
    cat <<EOF
Usage: $0 [options]

Required (or via env vars):
  --domain <value>                Domain name (CERTMGR_DOMAIN)
  --email <value>                 Let's Encrypt email (CERTMGR_EMAIL)
  --azure-tenant-id <value>       Azure tenant ID (CERTMGR_AZURE_TENANT_ID)
  --azure-client-id <value>       Azure client ID (CERTMGR_AZURE_CLIENT_ID)
  --azure-client-secret <value>   Azure client secret (CERTMGR_AZURE_CLIENT_SECRET)
  --azure-keyvault-name <value>   Azure Key Vault name (CERTMGR_AZURE_KEYVAULT_NAME)
  --azure-cert-name <value>       Azure certificate name (CERTMGR_AZURE_CERT_NAME)

Optional:
  --desec-token <value>           deSEC token (CERTMGR_DESEC_TOKEN)
  --cloudflare-email <value>      Cloudflare email (CERTMGR_CLOUDFLARE_EMAIL)
  --cloudflare-token <value>      Cloudflare token (CERTMGR_CLOUDFLARE_TOKEN)
  --renewal-mode <true|false>     Renewal mode (CERTMGR_RENEWAL_MODE, default: false)
  --staging <true|false>          Use staging LE env (CERTMGR_STAGING, default: false)
  --dns-provider <auto|desec|cloudflare>  DNS provider (CERTMGR_DNS_PROVIDER, default: auto)
  --stage <manual|export|upload>  Start from specific stage (CERTMGR_STAGE)
  --help                          Show this help
EOF
} n

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)
            DOMAIN="${2:-}"
            shift 2
            ;;
        --email)
            EMAIL="${2:-}"
            shift 2
            ;;
        --desec-token)
            DESEC_TOKEN="${2:-}"
            shift 2
            ;;
        --cloudflare-email)
            CLOUDFLARE_EMAIL="${2:-}"
            shift 2
            ;;
        --cloudflare-token)
            CLOUDFLARE_TOKEN="${2:-}"
            shift 2
            ;;
        --azure-tenant-id)
            AZURE_TENANT_ID="${2:-}"
            shift 2
            ;;
        --azure-client-id)
            AZURE_CLIENT_ID="${2:-}"
            shift 2
            ;;
        --azure-client-secret)
            AZURE_CLIENT_SECRET="${2:-}"
            shift 2
            ;;
        --azure-keyvault-name)
            AZURE_KEYVAULT_NAME="${2:-}"
            shift 2
            ;;
        --azure-cert-name)
            AZURE_CERT_NAME="${2:-}"
            shift 2
            ;;
        --renewal-mode)
            RENEWAL_MODE="${2:-}"
            shift 2
            ;;
        --staging)
            STAGING="${2:-}"
            shift 2
            ;;
        --dns-provider)
            DNS_PROVIDER="${2:-}"
            shift 2
            ;;
        --stage)
            RAW_STAGE="${2:-}"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            if [[ "$1" == --* ]]; then
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            fi
            if [ -z "${RAW_STAGE:-}" ]; then
                RAW_STAGE="$1"
                shift
            else
                echo "Unexpected positional argument: $1" >&2
                usage >&2
                exit 1
            fi
            ;;
    esac
done

STAGE="$RAW_STAGE"
if [[ "$STAGE" == stage=* ]]; then
    STAGE="${STAGE#stage=}"
fi
STAGE="${STAGE,,}"

echo "=== Certbot Azure Certificate Manager configuration ==="
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "deSEC Token: [Secret Hidden]"
echo "Cloudflare Email: $CLOUDFLARE_EMAIL"
echo "Cloudflare Token: [Secret Hidden]"
echo "Azure Tenant ID: $AZURE_TENANT_ID"
echo "Azure Client ID: $AZURE_CLIENT_ID"
echo "Azure Client Secret: [Secret Hidden]"
echo "Key Vault: $AZURE_KEYVAULT_NAME"
echo "Certificate Name: $AZURE_CERT_NAME"
echo "Renewal Mode: $RENEWAL_MODE"
echo "Staging: $STAGING"
echo "Keepalive: ${CERTMGR_KEEPALIVE:-false}"
echo "DNS Provider: $DNS_PROVIDER"
echo "Stage: ${STAGE:-full}"

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
    # Only validate domain and email for full or manual stages
    if [ -z "$STAGE" ] || [ "$STAGE" = "manual" ]; then
        [ -z "$DOMAIN" ] && missing_params+=("DOMAIN")
        [ -z "$EMAIL" ] && missing_params+=("EMAIL")
    fi
    [ -z "$AZURE_TENANT_ID" ] && missing_params+=("AZURE_TENANT_ID")
    [ -z "$AZURE_CLIENT_ID" ] && missing_params+=("AZURE_CLIENT_ID")
    [ -z "$AZURE_CLIENT_SECRET" ] && missing_params+=("AZURE_CLIENT_SECRET")
    [ -z "$AZURE_KEYVAULT_NAME" ] && missing_params+=("AZURE_KEYVAULT_NAME")
    [ -z "$AZURE_CERT_NAME" ] && missing_params+=("AZURE_CERT_NAME")

    if [ ${#missing_params[@]} -gt 0 ]; then
        log_error "Missing required parameters: ${missing_params[*]}"
        log_error "Use command line switches (for example: --domain, --email, --azure-tenant-id, --azure-client-id, --azure-client-secret, --azure-keyvault-name, --azure-cert-name)"
        log_error "Or set environment variables: CERTMGR_DOMAIN, CERTMGR_EMAIL, CERTMGR_DESEC_TOKEN, CERTMGR_CLOUDFLARE_EMAIL, CERTMGR_CLOUDFLARE_TOKEN, CERTMGR_AZURE_TENANT_ID, CERTMGR_AZURE_CLIENT_ID, CERTMGR_AZURE_CLIENT_SECRET, CERTMGR_AZURE_KEYVAULT_NAME, CERTMGR_AZURE_CERT_NAME, CERTMGR_DNS_PROVIDER, CERTMGR_STAGE"
        log_error "Optional stage values: manual, export, upload"
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
    mkdir -p "/etc/letsencrypt/$DOMAIN"
    
    case "$DNS_PROVIDER" in
        desec)
            if [ -z "$DESEC_TOKEN" ]; then
                log_error "deSEC provider selected but CERTMGR_DESEC_TOKEN is not set"
                error_exit
            fi
             desec_creds="/etc/letsencrypt/$DOMAIN/desec-credentials.ini"
            cat > "$desec_creds" <<EOF
dns_desec_token = $DESEC_TOKEN
EOF
            chmod 600 "$desec_creds"
            dns_args="--authenticator dns-desec --dns-desec-credentials $desec_creds --dns-desec-propagation-seconds 60"
            log_success "deSEC credentials validated"
            ;;
        cloudflare)
            if [ -z "$CLOUDFLARE_TOKEN" ]; then
                log_error "Cloudflare provider selected but CERTMGR_CLOUDFLARE_TOKEN is not set"
                error_exit
            fi
                certbot_creds="/etc/letsencrypt/$DOMAIN/certbot-credentials.ini"
                cat > "$certbot_creds" <<EOF
dns_cloudflare_email = $CLOUDFLARE_EMAIL
dns_cloudflare_api_token = $CLOUDFLARE_TOKEN
EOF
            chmod 600 "$certbot_creds"
            dns_args="--dns-cloudflare --dns-cloudflare-credentials $certbot_creds --dns-cloudflare-propagation-seconds 60"
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

    # Build certbot command
    local certbot_cmd="certbot certonly -v"
    if [ "$STAGING" = "true" ]; then
        log_info "Using Let's Encrypt staging environment"
        certbot_cmd="$certbot_cmd --staging"
    fi

    certbot_cmd="$certbot_cmd $dns_args"
    certbot_cmd="$certbot_cmd --non-interactive"
    certbot_cmd="$certbot_cmd --agree-tos"
    certbot_cmd="$certbot_cmd --email $EMAIL"
    certbot_cmd="$certbot_cmd --domain $DOMAIN"

    # Add force renewal flag if in renewal mode
    if [ "$RENEWAL_MODE" = "true" ]; then
        log_info "Running in renewal mode"
        certbot_cmd="$certbot_cmd --force-renewal"
    fi
    
    # Execute certbot
    log_info "Executing certbot command..."
    if eval "$certbot_cmd"; then
        rm -f "/etc/letsencrypt/$DOMAIN/*.ini"
        log_success "Certificate obtained successfully"
    else
        rm -f "/etc/letsencrypt/$DOMAIN/*.ini"
        log_error "Failed to obtain certificate"
        error_exit
  fi    
}

request_certificate_manual() {
    log_info "Starting manual interactive certificate request for domain: $DOMAIN"

    if [ ! -t 0 ] || [ ! -t 1 ]; then
        log_error "Manual stage requires an interactive TTY"
        log_error "Run container with -it and use --stage manual"
        error_exit
    fi

    local certbot_cmd="certbot certonly -v --manual --preferred-challenges dns"
    certbot_cmd="$certbot_cmd --manual-public-ip-logging-ok"
    certbot_cmd="$certbot_cmd --email $EMAIL"
    certbot_cmd="$certbot_cmd --domain $DOMAIN"

    if [ "$STAGING" = "true" ]; then
        log_info "Using Let's Encrypt staging environment"
        certbot_cmd="$certbot_cmd --staging"
    fi

    if [ "$RENEWAL_MODE" = "true" ]; then
        log_info "Running in renewal mode"
        certbot_cmd="$certbot_cmd --force-renewal"
    fi

    log_info "Launching interactive certbot manual flow..."
    if eval "$certbot_cmd"; then
        log_success "Manual certificate request completed successfully"
    else
        log_error "Manual certificate request failed"
        error_exit        
    fi    
}

export_certificates() {
    log_info "Exporting certificates to /mnt/secrets-output"
    
    # Determine certificate path
    local cert_path="/etc/letsencrypt/live/$DOMAIN"
    
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
    
    # Prefer certificates exported to mounted secrets, fallback to certbot live path
    local privkey_path="/mnt/secrets-output/privkey.pem"
    local fullchain_path="/mnt/secrets-output/fullchain.pem"
    if [[ ! -f "$privkey_path" || ! -f "$fullchain_path" ]]; then
        privkey_path="/etc/letsencrypt/live/$DOMAIN/privkey.pem"
        fullchain_path="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
    fi

    # Convert to PFX format
    openssl pkcs12 -export \
        -out "$pfx_file" \
        -inkey "$privkey_path" \
        -in "$fullchain_path" \
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

    case "$STAGE" in
        "")
            # Full flow
            validate_required_params
            setup_output_directory
            detect_dns_provider
            validate_provider_credentials
            request_certificate
            export_certificates
            upload_to_azure_keyvault
            ;;
        manual)
            log_info "Stage mode: manual (interactive certbot manual flow, then export/upload)"
            validate_required_params
            setup_output_directory
            request_certificate_manual
            export_certificates
            upload_to_azure_keyvault
            ;;
        export)
            log_info "Stage mode: export (starting from export_certificates)"
            validate_required_params
            export_certificates
            upload_to_azure_keyvault
            ;;
        upload)
            log_info "Stage mode: upload (starting from upload_to_azure_keyvault)"
            validate_required_params
            upload_to_azure_keyvault
            ;;
        *)
            log_error "Invalid stage: '$STAGE'. Supported values: export, upload"
            error_exit
            ;;
    esac
    
    log_success "=== Certificate management completed successfully ==="
    
    # Keep container alive if requested
    if [ "${CERTMGR_KEEPALIVE:-false}" = "true" ]; then
        run_keepalive
    fi
}

# Run main function
main
