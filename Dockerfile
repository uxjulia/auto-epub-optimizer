FROM node:lts-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY cli/package*.json cli/
RUN cd cli && npm ci --omit=dev

COPY cli/ cli/
COPY scripts/epub-optimizer.sh scripts/load-env.sh scripts/

RUN chmod +x scripts/epub-optimizer.sh scripts/load-env.sh

CMD ["bash", "scripts/epub-optimizer.sh"]
