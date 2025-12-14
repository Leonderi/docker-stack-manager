"""Teamspeak stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class TeamspeakStack(BaseStack):
    """Teamspeak 3 voice server stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="teamspeak",
            display_name="Teamspeak 3",
            description="Voice communication server",
            default_port=9987,  # UDP voice port
            required_env_vars=[
                "TS3SERVER_LICENSE",  # "accept" to accept license
            ],
            optional_env_vars={
                "TS3SERVER_SERVERADMIN_PASSWORD": "",  # Leave empty for auto-generated
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        # Note: Teamspeak uses UDP ports for voice, so Traefik routing is limited
        # The web query interface can be proxied, but voice goes directly to the VM
        return f"""version: '3.8'

services:
  teamspeak:
    image: teamspeak:latest
    container_name: teamspeak
    restart: unless-stopped
    ports:
      - "9987:9987/udp"      # Voice
      - "10011:10011"        # ServerQuery
      - "30033:30033"        # FileTransfer
    environment:
      - TS3SERVER_LICENSE=${{TS3SERVER_LICENSE}}
      - TS3SERVER_SERVERADMIN_PASSWORD=${{TS3SERVER_SERVERADMIN_PASSWORD}}
    volumes:
      - teamspeak-data:/var/ts3server

volumes:
  teamspeak-data:
"""

    def validate_config(self, config: StackConfig) -> tuple[bool, str]:
        """Validate Teamspeak config - license must be accepted."""
        valid, msg = super().validate_config(config)
        if not valid:
            return valid, msg

        if config.env_vars.get("TS3SERVER_LICENSE", "").lower() != "accept":
            return False, "You must accept the Teamspeak license (set TS3SERVER_LICENSE=accept)"

        return True, "Configuration valid"
