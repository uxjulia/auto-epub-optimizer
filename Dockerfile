FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends libcairo2 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cli/optimize.py cli/
COPY cli/epubkit_pipeline/ cli/epubkit_pipeline/
COPY scripts/epub-optimizer.sh scripts/load-env.sh scripts/

RUN chmod +x scripts/epub-optimizer.sh scripts/load-env.sh

CMD ["bash", "scripts/epub-optimizer.sh"]
