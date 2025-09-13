ARG KC_HOSTNAME
ARG KC_LOG_LEVEL=INFO
ARG KC_DB_URL_DATABASE
# Keycloak OpenMemory Authentication Provider
FROM quay.io/keycloak/keycloak:26.3.4

ARG KC_HOSTNAME
ARG KC_LOG_LEVEL
# Set environment variables with defaults for development
ENV KC_DB=postgres
ENV KC_DB_URL_HOST=postgres
ENV KC_DB_URL_DATABASE=${KC_DB_URL_DATABASE}
ENV KC_HOSTNAME=${KC_HOSTNAME}
ENV KC_HTTP_ENABLED=false
#ENV KC_HTTP_PORT=8080
ENV KC_HTTPS_PORT=8443
#ENV KC_HEALTH_ENABLED=true
#ENV KC_METRICS_ENABLED=true
ENV KC_LOG_LEVEL=${KC_LOG_LEVEL}

# Create a non-root user for security
USER 1000:1000

COPY --chown=1000:1000 keycloak.conf /opt/keycloak/conf/keycloak.conf
COPY --chown=1000:1000 start.sh /opt/keycloak/start.sh

# Configure Keycloak for production-ready deployment
RUN /opt/keycloak/bin/kc.sh build
RUN /opt/keycloak/bin/kc.sh show-config

# Expose ports
EXPOSE 8443

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f https://localhost:8443/health/ready || exit 1
# Start Keycloak with optimized configuration
ENTRYPOINT ["/opt/keycloak/start.sh"]
#ENTRYPOINT ["/bin/bash"]