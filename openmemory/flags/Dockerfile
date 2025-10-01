ARG FLAGSMITH_TAG=latest

FROM docker.flagsmith.com/flagsmith/flagsmith:${FLAGSMITH_TAG}

# This image contains the full Flagsmith stack (API + frontend) and is maintained by
# the Flagsmith team. Customize runtime configuration exclusively through environment
# variables documented at:
# API: https://docs.flagsmith.com/deployment/locally-api#environment-variables
# UI:  https://docs.flagsmith.com/deployment/locally-frontend#environment-variables

# Override FLAGSMITH_TAG at build time if you need a pinned release, e.g.:
#   docker build --build-arg FLAGSMITH_TAG=2.197.0 -t flagsmith .