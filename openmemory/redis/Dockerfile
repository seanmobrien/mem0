ARG REDIS_VERSION=latest
FROM redis/redis-stack-server:${REDIS_VERSION}

# Ensure openssl is available for TLS key/cert handling
RUN apt-get update \ 
  && apt-get install -y --no-install-recommends openssl \
  && rm -rf /var/lib/apt/lists/*

# Entrypoint to load password from a mounted secret and pass it via REDIS_ARGS.
# Falls back to the upstream entrypoint once REDIS_ARGS is set.
COPY redis-stack-server-entrypoint.sh /usr/local/bin/redis-stack-entrypoint.sh
RUN chmod +x /usr/local/bin/redis-stack-entrypoint.sh

EXPOSE 16379

ENTRYPOINT ["/usr/local/bin/redis-stack-entrypoint.sh"]
CMD ["redis-server"]
