"""Stack definitions - import all to register them."""

from .traefik import TraefikStack
from .influxdb import InfluxDBStack
from .grafana import GrafanaStack
from .vaultwarden import VaultwardenStack
from .hemmelig import HemmeligStack
from .netbox import NetboxStack
from .n8n import N8NStack
from .teamspeak import TeamspeakStack
from .mqtt import MQTTStack
from .paperless import PaperlessStack
from .odoo import OdooStack

__all__ = [
    "TraefikStack",
    "InfluxDBStack",
    "GrafanaStack",
    "VaultwardenStack",
    "HemmeligStack",
    "NetboxStack",
    "N8NStack",
    "TeamspeakStack",
    "MQTTStack",
    "PaperlessStack",
    "OdooStack",
]
