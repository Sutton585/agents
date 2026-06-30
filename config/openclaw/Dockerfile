FROM ghcr.io/openclaw/openclaw:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends make gcc g++ jq ripgrep ffmpeg \
    && npm install -g @tobilu/qmd \
    && apt-get purge -y --auto-remove make gcc g++ \
    && rm -rf /var/lib/apt/lists/*

USER node
