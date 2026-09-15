FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/beacon

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /opt/beacon/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn psycopg2-binary

COPY . /opt/beacon

RUN mkdir -p \
      /etc/beacon \
      /var/lib/beacon \
      /var/log/beacon \
      /usr/local/lib/beacon/voice_providers

COPY docker/beacon.docker.conf /etc/beacon/beacon.conf
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENV BEACON_CONFIG_FILE=/etc/beacon/beacon.conf
ENV BEACON_SERVICE=web

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
