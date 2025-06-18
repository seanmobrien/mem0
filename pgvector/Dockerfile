# Define the base image
FROM schoollawregistry.azurecr.io/timescale/timescaledb:latest AS base
RUN mkdir -p /app \
    && addgroup --system --gid 1001 nextjs \
    && adduser --system --uid 1001 nextjs \
    && chown -R nextjs:nextjs /app
WORKDIR /app

# Install dependencies only when needed
FROM base AS deps
# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine to understand why libc6-compat might be needed.
RUN apk add --no-cache libc6-compat 

# Install Node.js
RUN apk add --no-cache nodejs npm

# Verify Node.js installation
RUN node -v && npm -v
RUN npm install -g yarn@latest

COPY ./hello-world-im-postgresql/package.json ./hello-world-im-postgresql/yarn.lock* ./hello-world-im-postgresql/package-lock.json* ./hello-world-im-postgresql/pnpm-lock.yaml* ./hello-world-im-postgresql/.npmrc* ./
RUN \
  if [ -f yarn.lock ]; then yarn --frozen-lockfile; \
  elif [ -f package-lock.json ]; then npm ci; \
  elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm i --frozen-lockfile; \
  else echo "Lockfile not found." && exit 1; \
  fi


# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app

# Install Node.js
RUN apk add --no-cache nodejs npm

# Verify Node.js installation
RUN node -v && npm -v
RUN npm install -g typescript@latest yarn@latest

COPY --from=deps /app/node_modules ./node_modules
COPY ./hello-world-im-postgresql  .
#COPY ./hello-world-im-postgresql/src ./src
#COPY ./hello-world-im-postgresql/public ./public

# Next.js collects completely anonymous telemetry data about general usage.
# Learn more here: https://nextjs.org/telemetry
# Uncomment the following line in case you want to disable telemetry during the build.
ENV NEXT_TELEMETRY_DISABLED=1
ENV FOR_STANDALONE=1
ENV IS_BUILDING=1

RUN \
  if [ -f yarn.lock ]; then yarn run build; \
  elif [ -f package-lock.json ]; then npm run build; \
  elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm run build; \
  else echo "Lockfile not found." && exit 1; \
  fi

# Production image
#FROM schoollawregistry.azurecr.io/timescale/timescaledb:latest AS production
FROM schoollawregistry.azurecr.io/timescale/timescaledb:latest AS production

RUN apk add --no-cache nodejs npm \
    && npm install -g typescript@latest vercel@latest yarn@latest \
    && mkdir -p /home/nextjs \
    && addgroup --system --gid 1001 nextjs \
    && adduser --system --uid 1001 nextjs \
    && chown -R nextjs:nextjs /home/nextjs

WORKDIR /home/nextjs

COPY --from=builder /app/.next /home/nextjs/.next
COPY --from=builder /app/node_modules /home/nextjs/node_modules
COPY --from=builder /app/package.json /home/nextjs/package.json

RUN chown -R nextjs:nextjs /home/nextjs/.next \
    && chown -R nextjs:nextjs /home/nextjs/package.json

ENV NODE_ENV=production
ENV FOR_STANDALONE=1
ENV NEXT_TELEMETRY_DISABLED=1

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV PGDATA=/var/lib/postgresql/17/docker

CMD ["yarn", "start"]
