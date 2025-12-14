"""Hemmelig stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class HemmeligStack(BaseStack):
    """Hemmelig secret sharing stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="hemmelig",
            display_name="Hemmelig",
            description="Self-hosted secret sharing service",
            default_port=3000,
            required_env_vars=[
                "SECRET_MASTER_KEY",
            ],
            optional_env_vars={
                "SECRET_MAX_TEXT_SIZE": "256",
                "RATE_LIMIT_ENABLED": "true",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  hemmelig:
    image: hemmeligapp/hemmelig:latest
    container_name: hemmelig
    restart: unless-stopped
    ports:
      - "{config.port}:3000"
    environment:
      - SECRET_MASTER_KEY=${{SECRET_MASTER_KEY}}
      - SECRET_MAX_TEXT_SIZE=${{SECRET_MAX_TEXT_SIZE}}
      - RATE_LIMIT_ENABLED=${{RATE_LIMIT_ENABLED}}
    volumes:
      - hemmelig-data:/var/lib/hemmelig/database

volumes:
  hemmelig-data:
"""
