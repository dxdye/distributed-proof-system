# Sandbox image for building and analysing untrusted Lean repositories (SR-20).
#
# The image is built in a *trusted* step (with network access). Containers
# started from it run with --network none, a read-only root filesystem, a
# read-only source tree, dropped capabilities and resource limits; see
# dpc/lean/executor.py (DockerExecutor.run_argv).
#
# One image per Lean toolchain: .olean files are bound to the exact Lean
# version, so the analyzer is compiled for the same toolchain here.
FROM debian:bookworm-slim

ARG LEAN_TOOLCHAIN

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 lean
USER lean
ENV ELAN_HOME=/home/lean/.elan
ENV PATH=/home/lean/.elan/bin:$PATH

RUN curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -o /tmp/elan-init.sh \
 && sh /tmp/elan-init.sh -y --default-toolchain "$LEAN_TOOLCHAIN" --no-modify-path \
 && rm /tmp/elan-init.sh \
 && lean --version

COPY --chown=lean:lean lean/analyzer /opt/dpc/analyzer
COPY --chown=lean:lean sandbox/analyze.sh /opt/dpc/analyze.sh

RUN cd /opt/dpc/analyzer \
 && rm -rf .lake \
 && echo "$LEAN_TOOLCHAIN" > lean-toolchain \
 && lake build \
 && chmod 0555 /opt/dpc/analyze.sh

WORKDIR /work
