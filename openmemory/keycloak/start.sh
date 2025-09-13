#!/bin/sh

cd /opt/keycloak
./bin/kc.sh show-config
./bin/kc.sh start --optimized