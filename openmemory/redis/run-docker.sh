#!/bin/sh
set -eu

NAME=school-law-redis
MODE=${1:-}
SYSCTL=""

# Detect if vm.overcommit_memory sysctl is allowed; fallback gracefully if denied.
if docker run --rm --entrypoint /bin/true --sysctl vm.overcommit_memory=1 redis:school-lawyer >/dev/null 2>&1; then
	SYSCTL="--sysctl vm.overcommit_memory=1"
else
	echo "warning: vm.overcommit_memory sysctl not allowed; continuing without it" >&2
fi

if [ "$(docker ps -q -f name="^${NAME}$")" ]; then
	docker stop "$NAME"
	docker rm "$NAME"
elif [ "$(docker ps -aq -f name="^${NAME}$")" ]; then
	docker rm "$NAME"
fi

if [ "$MODE" = "interactive" ]; then
	docker run $SYSCTL --name "$NAME" -p 16379:16379 -p 16380:16380 -v ./secrets/REDIS_PW:/run/secrets/REDIS_PW:ro -it redis:school-lawyer
else

	docker run $SYSCTL -d --name "$NAME" -p 16379:16379 -p 16380:16380 -v ./secrets/REDIS_PW:/run/secrets/REDIS_PW:ro redis:school-lawyer
fi