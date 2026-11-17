# The DPC web service (coordination service with the built web client) as an
# image, for compose.yaml at the repository root. Build context: the repository
# root; what the build may see is listed in Dockerfile.dockerignore next to this
# file. The service runs neither Lean nor Docker: it serves recorded views.

# --- Web client -> web/dist
FROM node:22-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- Python environment exactly as locked in pixi.lock, plus the service
FROM ghcr.io/prefix-dev/pixi:0.68.1 AS app
WORKDIR /app
COPY pixi.toml pixi.lock ./
RUN pixi install --frozen -e default
COPY dpc/ dpc/
COPY config/ config/
COPY --from=web /src/web/dist web/dist
COPY deploy/dpc/entrypoint.sh /usr/local/bin/dpc-entrypoint.sh
# Guard against CRLF line endings from a Windows checkout.
RUN sed -i 's/\r$//' /usr/local/bin/dpc-entrypoint.sh
ENV DPC_DATA=/data
EXPOSE 8000
ENTRYPOINT ["sh", "/usr/local/bin/dpc-entrypoint.sh"]
