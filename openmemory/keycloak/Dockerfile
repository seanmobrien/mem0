# Keycloak OpenMemory Authentication Provider
FROM quay.io/keycloak/keycloak:26.0.7

# Set environment variables with defaults for development
ENV KC_DB=postgres
ENV KC_DB_URL_HOST=postgres
ENV KC_DB_URL_DATABASE=keycloak
ENV KC_DB_USERNAME=keycloak
ENV KC_DB_PASSWORD=keycloak
ENV KC_HOSTNAME=localhost
ENV KC_HTTP_ENABLED=true
ENV KC_HTTP_PORT=8080
ENV KC_HTTPS_PORT=8443
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true
ENV KC_LOG_LEVEL=INFO

# Create a non-root user for security
USER 1000:1000

# Configure Keycloak for production-ready deployment
RUN /opt/keycloak/bin/kc.sh build

# Expose ports
EXPOSE 8080 8443

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health/ready || exit 1

# Start Keycloak with optimized configuration
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]