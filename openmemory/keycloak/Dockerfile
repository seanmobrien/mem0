ARG KC_LOG_LEVEL=INFO
ARG KC_DB_URL_DATABASE=keycloak
# Keycloak OpenMemory Authentication Provider
FROM quay.io/keycloak/keycloak:26.3.4

ARG KC_DB_URL_DATABASE
ARG KC_LOG_LEVEL
# Set environment variables with defaults for development
ENV KC_DB=postgres
ENV KC_DB_URL_DATABASE=${KC_DB_URL_DATABASE}
ENV KC_HTTP_ENABLED=true
ENV KC_HTTPS_ENABLED=true
ENV KC_HTTP_PORT=8080
ENV KC_HTTPS_PORT=8443
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true
ENV KC_LOG_LEVEL=${KC_LOG_LEVEL}

# Create a non-root user for security
USER 1000:1000

COPY --chown=1000:1000 keycloak.conf /opt/keycloak/conf/keycloak.conf
COPY --chown=1000:1000 start.sh /opt/keycloak/start.sh

# Configure Keycloak for production-ready deployment
RUN chmod +x /opt/keycloak/start.sh && \
    /opt/keycloak/bin/kc.sh build && \
    /opt/keycloak/bin/kc.sh show-config

# Expose ports
EXPOSE 8080 8443 9000

# Start Keycloak with optimized configuration
ENTRYPOINT ["/opt/keycloak/start.sh"]