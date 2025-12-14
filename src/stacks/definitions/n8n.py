"""n8n stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class N8NStack(BaseStack):
    """n8n workflow automation stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="n8n",
            display_name="n8n",
            description="Workflow automation platform",
            default_port=5678,
            required_env_vars=[
                "N8N_BASIC_AUTH_USER",
                "N8N_BASIC_AUTH_PASSWORD",
            ],
            optional_env_vars={
                "N8N_BASIC_AUTH_ACTIVE": "true",
                "N8N_HOST": "localhost",
                "N8N_PROTOCOL": "https",
                "GENERIC_TIMEZONE": "Europe/Berlin",
                "N8N_ENCRYPTION_KEY": "",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  n8n:
    image: n8nio/n8n:latest
    container_name: n8n
    restart: unless-stopped
    ports:
      - "{config.port}:5678"
    environment:
      - N8N_BASIC_AUTH_ACTIVE=${{N8N_BASIC_AUTH_ACTIVE}}
      - N8N_BASIC_AUTH_USER=${{N8N_BASIC_AUTH_USER}}
      - N8N_BASIC_AUTH_PASSWORD=${{N8N_BASIC_AUTH_PASSWORD}}
      - N8N_HOST=${{N8N_HOST}}
      - N8N_PROTOCOL=${{N8N_PROTOCOL}}
      - N8N_ENCRYPTION_KEY=${{N8N_ENCRYPTION_KEY}}
      - GENERIC_TIMEZONE=${{GENERIC_TIMEZONE}}
      - WEBHOOK_URL=https://{config.subdomain}.${{DOMAIN}}/
    volumes:
      - n8n-data:/home/node/.n8n

volumes:
  n8n-data:
"""
