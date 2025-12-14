"""Grafana stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class GrafanaStack(BaseStack):
    """Grafana visualization and monitoring stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="grafana",
            display_name="Grafana",
            description="Visualization and monitoring platform",
            default_port=3000,
            required_env_vars=[
                "GF_SECURITY_ADMIN_PASSWORD",
            ],
            optional_env_vars={
                "GF_SECURITY_ADMIN_USER": "admin",
                "GF_USERS_ALLOW_SIGN_UP": "false",
                "GF_SERVER_ROOT_URL": "",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: unless-stopped
    ports:
      - "{config.port}:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=${{GF_SECURITY_ADMIN_USER}}
      - GF_SECURITY_ADMIN_PASSWORD=${{GF_SECURITY_ADMIN_PASSWORD}}
      - GF_USERS_ALLOW_SIGN_UP=${{GF_USERS_ALLOW_SIGN_UP}}
      - GF_SERVER_ROOT_URL=${{GF_SERVER_ROOT_URL}}
    volumes:
      - grafana-data:/var/lib/grafana
      - grafana-provisioning:/etc/grafana/provisioning

volumes:
  grafana-data:
  grafana-provisioning:
"""
