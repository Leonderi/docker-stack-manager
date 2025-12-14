"""Netbox stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class NetboxStack(BaseStack):
    """Netbox DCIM/IPAM stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="netbox",
            display_name="Netbox",
            description="Data center infrastructure management (DCIM) and IPAM",
            default_port=8000,
            required_env_vars=[
                "SUPERUSER_NAME",
                "SUPERUSER_EMAIL",
                "SUPERUSER_PASSWORD",
                "SECRET_KEY",
            ],
            optional_env_vars={
                "ALLOWED_HOST": "*",
                "DB_NAME": "netbox",
                "DB_USER": "netbox",
                "DB_PASSWORD": "netbox",
                "REDIS_PASSWORD": "netbox",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  netbox:
    image: netboxcommunity/netbox:latest
    container_name: netbox
    restart: unless-stopped
    ports:
      - "{config.port}:8080"
    environment:
      - SUPERUSER_NAME=${{SUPERUSER_NAME}}
      - SUPERUSER_EMAIL=${{SUPERUSER_EMAIL}}
      - SUPERUSER_PASSWORD=${{SUPERUSER_PASSWORD}}
      - ALLOWED_HOST=${{ALLOWED_HOST}}
      - SECRET_KEY=${{SECRET_KEY}}
      - DB_HOST=netbox-postgres
      - DB_NAME=${{DB_NAME}}
      - DB_USER=${{DB_USER}}
      - DB_PASSWORD=${{DB_PASSWORD}}
      - REDIS_HOST=netbox-redis
      - REDIS_PASSWORD=${{REDIS_PASSWORD}}
    volumes:
      - netbox-media:/opt/netbox/netbox/media
      - netbox-reports:/opt/netbox/netbox/reports
      - netbox-scripts:/opt/netbox/netbox/scripts
    depends_on:
      - netbox-postgres
      - netbox-redis

  netbox-postgres:
    image: postgres:15-alpine
    container_name: netbox-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=${{DB_NAME}}
      - POSTGRES_USER=${{DB_USER}}
      - POSTGRES_PASSWORD=${{DB_PASSWORD}}
    volumes:
      - netbox-postgres-data:/var/lib/postgresql/data

  netbox-redis:
    image: redis:7-alpine
    container_name: netbox-redis
    restart: unless-stopped
    command: redis-server --requirepass ${{REDIS_PASSWORD}}
    volumes:
      - netbox-redis-data:/data

volumes:
  netbox-media:
  netbox-reports:
  netbox-scripts:
  netbox-postgres-data:
  netbox-redis-data:
"""
