FROM neo4j:5.26.13

RUN apt-get update && \
    apt-get install -y ca-certificates curl apt-transport-https lsb-release gnupg && \
    curl -sL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | tee /etc/apt/trusted.gpg.d/microsoft.gpg > /dev/null && \
    echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/azure-cli.list && \
    apt-get update && \
    apt-get install -y azure-cli && \
    rm -rf /var/lib/apt/lists/*

COPY extension_script.sh /extension_script.sh
ENV EXTENSION_SCRIPT=/extension_script.sh
ENV NEO4J_PLUGINS='["apoc"]'
ENV NEO4J_apoc_export_file_enabled=true
ENV NEO4J_apoc_import_file_enabled=true
ENV NEO4J_apoc_import_file_use__neo4j__config=true
# BOLT SSL
ENV NEO4J_server_bolt_listen__address=0.0.0.0:7687
ENV NEO4J_dbms_ssl_policy_bolt_enabled=true
ENV NEO4J_dbms_ssl_policy_bolt_base__directory=certificates/bolt
ENV NEO4J_dbms_ssl_policy_bolt_private__key=bolt.key
ENV NEO4J_dbms_ssl_policy_bolt_public__certificate=bolt.crt
#Memory
#ENV NEO4J_server_memory_heap_initial__size='500m'
#ENV NEO4J_server_memory_heap_max__size='1500m'
#ENV NEO4J_server_memory_pagecache_size='1g'

#Additional Ops 
#ENV NEO4J_server_jvm_additional='-XX:+ExitOnOutOfMemoryError'


RUN mkdir /var/lib/neo4j/certificates/bolt \
    && mkdir /var/lib/neo4j/certificates/bolt/trusted \
    && mkdir /var/lib/neo4j/certificates/bolt/revoked

EXPOSE 7474 7687