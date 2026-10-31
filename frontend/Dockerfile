# The `proxy` service: Caddy with the built web app. No Node at runtime, it only serves files.
# Build context is the repository root (it needs deploy/Caddyfile).

FROM node:22-alpine AS build
WORKDIR /srv/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_DEVELOPING_STRIP=false
RUN VITE_DEVELOPING_STRIP=$VITE_DEVELOPING_STRIP npm run build

FROM caddy:2
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /srv/frontend/dist /srv/www
