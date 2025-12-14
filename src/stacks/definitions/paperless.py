"""Paperless-ngx stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class PaperlessStack(BaseStack):
    """Paperless-ngx document management stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="paperless",
            display_name="Paperless-ngx",
            description="Document management system with OCR",
            default_port=8000,
            required_env_vars=[
                "PAPERLESS_ADMIN_USER",
                "PAPERLESS_ADMIN_PASSWORD",
                "PAPERLESS_SECRET_KEY",
            ],
            optional_env_vars={
                "PAPERLESS_OCR_LANGUAGE": "deu+eng",
                "PAPERLESS_TIME_ZONE": "Europe/Berlin",
                "PAPERLESS_CONSUMER_POLLING": "30",
                "PAPERLESS_CONSUMER_RECURSIVE": "true",
                "PAPERLESS_DBHOST": "paperless-db",
                "PAPERLESS_REDIS": "redis://paperless-redis:6379",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  paperless:
    image: ghcr.io/paperless-ngx/paperless-ngx:latest
    container_name: paperless
    restart: unless-stopped
    ports:
      - "{config.port}:8000"
    environment:
      - PAPERLESS_ADMIN_USER=${{PAPERLESS_ADMIN_USER}}
      - PAPERLESS_ADMIN_PASSWORD=${{PAPERLESS_ADMIN_PASSWORD}}
      - PAPERLESS_SECRET_KEY=${{PAPERLESS_SECRET_KEY}}
      - PAPERLESS_OCR_LANGUAGE=${{PAPERLESS_OCR_LANGUAGE}}
      - PAPERLESS_TIME_ZONE=${{PAPERLESS_TIME_ZONE}}
      - PAPERLESS_CONSUMER_POLLING=${{PAPERLESS_CONSUMER_POLLING}}
      - PAPERLESS_CONSUMER_RECURSIVE=${{PAPERLESS_CONSUMER_RECURSIVE}}
      - PAPERLESS_REDIS=${{PAPERLESS_REDIS}}
      - PAPERLESS_DBHOST=${{PAPERLESS_DBHOST}}
      - PAPERLESS_TIKA_ENABLED=1
      - PAPERLESS_TIKA_GOTENBERG_ENDPOINT=http://paperless-gotenberg:3000
      - PAPERLESS_TIKA_ENDPOINT=http://paperless-tika:9998
    volumes:
      - paperless-data:/usr/src/paperless/data
      - paperless-media:/usr/src/paperless/media
      - paperless-export:/usr/src/paperless/export
      - paperless-consume:/usr/src/paperless/consume
    depends_on:
      - paperless-db
      - paperless-redis
      - paperless-gotenberg
      - paperless-tika

  paperless-db:
    image: postgres:15-alpine
    container_name: paperless-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=paperless
      - POSTGRES_USER=paperless
      - POSTGRES_PASSWORD=paperless
    volumes:
      - paperless-pgdata:/var/lib/postgresql/data

  paperless-redis:
    image: redis:7-alpine
    container_name: paperless-redis
    restart: unless-stopped
    volumes:
      - paperless-redisdata:/data

  paperless-gotenberg:
    image: gotenberg/gotenberg:8
    container_name: paperless-gotenberg
    restart: unless-stopped
    command:
      - "gotenberg"
      - "--chromium-disable-javascript=true"
      - "--chromium-allow-list=file:///tmp/.*"

  paperless-tika:
    image: ghcr.io/paperless-ngx/tika:latest
    container_name: paperless-tika
    restart: unless-stopped

volumes:
  paperless-data:
  paperless-media:
  paperless-export:
  paperless-consume:
  paperless-pgdata:
  paperless-redisdata:
"""
