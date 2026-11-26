FROM node:22.23.4-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates python3-venv \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/modelswarm
COPY cli/pyproject.toml cli/pyproject.toml
COPY cli/src cli/src
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -e cli
RUN corepack enable && cd cli/src/modelswarm/bridge && corepack yarn install --immutable
COPY cli/demo/*.mjs cli/demo/*.py cli/demo/
RUN install -d -o node -g node -m 0700 /data
ENV PATH="/opt/venv/bin:$PATH"
USER node
