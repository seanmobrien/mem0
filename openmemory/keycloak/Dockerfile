ARG KC_LOG_LEVEL=INFO
ARG KC_DB_URL_DATABASE=keycloak

# Builder to assemble provider JAR with minimal footprint
FROM alpine:3.19 AS provider-builder
RUN apk add --no-cache fastjar
WORKDIR /workspace
# Bring in all provider assets and the script package once; build the JS policy jar inside the builder
COPY packages/ packages/
RUN fastjar cf packages/providers/kc-casefile-js-policy.jar \
    packages/kc-casefile-js-policy/META-INF/keycloak-scripts.json \
    packages/kc-casefile-js-policy/compliance-theater-2000-case-file-acl.js

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
COPY --from=provider-builder --chown=1000:1000 /workspace/packages/providers /opt/keycloak/providers

# Configure Keycloak for production-ready deployment
RUN chmod +x /opt/keycloak/start.sh && \
    /opt/keycloak/bin/kc.sh build && \
    /opt/keycloak/bin/kc.sh show-config

# Expose ports
EXPOSE 8080 8443 9000

# Start Keycloak with optimized configuration
ENTRYPOINT ["/opt/keycloak/start.sh"]
