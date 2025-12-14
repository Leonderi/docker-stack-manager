"""Odoo ERP stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class OdooStack(BaseStack):
    """Odoo ERP/CRM stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="odoo",
            display_name="Odoo",
            description="Open source ERP and CRM platform",
            default_port=8069,
            required_env_vars=[
                "POSTGRES_PASSWORD",
            ],
            optional_env_vars={
                "POSTGRES_USER": "odoo",
                "POSTGRES_DB": "postgres",
                "ODOO_EMAIL": "admin@example.com",
                "ODOO_PASSWORD": "admin",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  odoo:
    image: odoo:17
    container_name: odoo
    restart: unless-stopped
    ports:
      - "{config.port}:8069"
      - "8072:8072"
    environment:
      - HOST=odoo-db
      - USER=${{POSTGRES_USER}}
      - PASSWORD=${{POSTGRES_PASSWORD}}
    volumes:
      - odoo-web-data:/var/lib/odoo
      - odoo-config:/etc/odoo
      - odoo-addons:/mnt/extra-addons
    depends_on:
      - odoo-db

  odoo-db:
    image: postgres:15-alpine
    container_name: odoo-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=${{POSTGRES_DB}}
      - POSTGRES_USER=${{POSTGRES_USER}}
      - POSTGRES_PASSWORD=${{POSTGRES_PASSWORD}}
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - odoo-db-data:/var/lib/postgresql/data/pgdata

volumes:
  odoo-web-data:
  odoo-config:
  odoo-addons:
  odoo-db-data:
"""
