"""MQTT (Mosquitto) stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class MQTTStack(BaseStack):
    """Eclipse Mosquitto MQTT broker stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="mqtt",
            display_name="Mosquitto MQTT",
            description="Lightweight MQTT message broker",
            default_port=1883,
            required_env_vars=[],  # Basic setup needs no env vars
            optional_env_vars={
                "MQTT_USER": "",
                "MQTT_PASSWORD": "",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  mosquitto:
    image: eclipse-mosquitto:latest
    container_name: mosquitto
    restart: unless-stopped
    ports:
      - "{config.port}:1883"      # MQTT
      - "9001:9001"               # WebSocket
    volumes:
      - mosquitto-data:/mosquitto/data
      - mosquitto-log:/mosquitto/log
      - mosquitto-config:/mosquitto/config

volumes:
  mosquitto-data:
  mosquitto-log:
  mosquitto-config:
"""

    def deploy(self, vm, config):
        """Deploy MQTT with custom mosquitto.conf."""
        # First deploy normally
        result = super().deploy(vm, config)
        if not result[0]:
            return result

        # Create basic config if credentials are provided
        mqtt_user = config.env_vars.get("MQTT_USER", "")
        mqtt_pass = config.env_vars.get("MQTT_PASSWORD", "")

        if mqtt_user and mqtt_pass:
            stack_path = self.get_stack_path(vm)

            # Create mosquitto.conf
            mosquitto_conf = """listener 1883
listener 9001
protocol websockets

allow_anonymous false
password_file /mosquitto/config/passwd
"""
            self.ssh.upload_content(
                vm,
                mosquitto_conf,
                f"{stack_path}/mosquitto.conf"
            )

            # Create password file (mosquitto_passwd format)
            # Note: In production, use proper hashing
            passwd_content = f"{mqtt_user}:{mqtt_pass}"
            self.ssh.upload_content(vm, passwd_content, f"{stack_path}/passwd")

            # Copy config into container volume
            self.ssh.run_command(
                vm,
                f"docker cp {stack_path}/mosquitto.conf mosquitto:/mosquitto/config/mosquitto.conf"
            )
            self.ssh.run_command(
                vm,
                f"docker cp {stack_path}/passwd mosquitto:/mosquitto/config/passwd"
            )

            # Restart to apply config
            self.docker.restart_container(vm, "mosquitto")

        return result
