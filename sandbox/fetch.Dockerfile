# Minimal image for the trusted fetch step: git only, no Lean, no Lake.
# Containers from it run with network access but never execute repository code.
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 lean \
 && mkdir /ws && chown 1000:1000 /ws
USER lean
WORKDIR /ws
