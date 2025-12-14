"""Vaultwarden stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class VaultwardenStack(BaseStack):
    """Vaultwarden (Bitwarden-compatible) password manager stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="vaultwarden",
            display_name="Vaultwarden",
            description="Self-hosted Bitwarden-compatible password manager",
            default_port=8080,
            required_env_vars=[
                "ADMIN_TOKEN",
            ],
            optional_env_vars={
                "SIGNUPS_ALLOWED": "false",
                "INVITATIONS_ALLOWED": "true",
                "SHOW_PASSWORD_HINT": "false",
                "WEBSOCKET_ENABLED": "true",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden
    restart: unless-stopped
    ports:
      - "{config.port}:80"
      - "{config.port + 1}:3012"
    environment:
      - ADMIN_TOKEN=${{ADMIN_TOKEN}}
      - SIGNUPS_ALLOWED=${{SIGNUPS_ALLOWED}}
      - INVITATIONS_ALLOWED=${{INVITATIONS_ALLOWED}}
      - SHOW_PASSWORD_HINT=${{SHOW_PASSWORD_HINT}}
      - WEBSOCKET_ENABLED=${{WEBSOCKET_ENABLED}}
    volumes:
      - vaultwarden-data:/data

volumes:
  vaultwarden-data:
"""
