FROM python:3.11-slim

WORKDIR /app

# Install minimal packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy repo files (assumes compose mounts the full project over /app in dev)
COPY . /app

RUN pip install --no-cache-dir psycopg2-binary

COPY docker/migration-cron/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/entrypoint.sh"]
