"""InfluxDB v2 stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack


@register_stack
class InfluxDBStack(BaseStack):
    """InfluxDB v2 time series database stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="influxdb",
            display_name="InfluxDB v2",
            description="Time series database for metrics and events",
            default_port=8086,
            required_env_vars=[
                "DOCKER_INFLUXDB_INIT_USERNAME",
                "DOCKER_INFLUXDB_INIT_PASSWORD",
                "DOCKER_INFLUXDB_INIT_ORG",
                "DOCKER_INFLUXDB_INIT_BUCKET",
            ],
            optional_env_vars={
                "DOCKER_INFLUXDB_INIT_MODE": "setup",
                "DOCKER_INFLUXDB_INIT_RETENTION": "0",
            },
        )

    def generate_compose(self, config: StackConfig) -> str:
        return f"""version: '3.8'

services:
  influxdb:
    image: influxdb:2
    container_name: influxdb
    restart: unless-stopped
    ports:
      - "{config.port}:8086"
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=${{DOCKER_INFLUXDB_INIT_MODE}}
      - DOCKER_INFLUXDB_INIT_USERNAME=${{DOCKER_INFLUXDB_INIT_USERNAME}}
      - DOCKER_INFLUXDB_INIT_PASSWORD=${{DOCKER_INFLUXDB_INIT_PASSWORD}}
      - DOCKER_INFLUXDB_INIT_ORG=${{DOCKER_INFLUXDB_INIT_ORG}}
      - DOCKER_INFLUXDB_INIT_BUCKET=${{DOCKER_INFLUXDB_INIT_BUCKET}}
      - DOCKER_INFLUXDB_INIT_RETENTION=${{DOCKER_INFLUXDB_INIT_RETENTION}}
    volumes:
      - influxdb-data:/var/lib/influxdb2
      - influxdb-config:/etc/influxdb2

volumes:
  influxdb-data:
  influxdb-config:
"""
