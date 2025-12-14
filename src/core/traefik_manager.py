"""Traefik configuration and deployment manager."""

from dataclasses import dataclass
from typing import Optional

import yaml

from .config_loader import Settings, VMConfig, get_config_loader
from .docker_manager import DockerManager, get_docker_manager
from .ssh_manager import SSHManager, get_ssh_manager


TRAEFIK_BASE_PATH = "/opt/traefik"
TRAEFIK_DYNAMIC_PATH = f"{TRAEFIK_BASE_PATH}/dynamic"


@dataclass
class ServiceRoute:
    """A route configuration for a service."""
    name: str
    subdomain: str
    target_host: str
    target_port: int
    https: bool = True
    middlewares: list[str] = None

    def __post_init__(self):
        if self.middlewares is None:
            self.middlewares = []


class TraefikManager:
    """Manages Traefik deployment and configuration."""

    def __init__(
        self,
        ssh_manager: Optional[SSHManager] = None,
        docker_manager: Optional[DockerManager] = None
    ):
        """Initialize Traefik manager."""
        self.ssh = ssh_manager or get_ssh_manager()
        self.docker = docker_manager or get_docker_manager()
        self.config_loader = get_config_loader()

    def _get_traefik_vm(self) -> VMConfig:
        """Get the Traefik VM configuration."""
        vms = self.config_loader.load_vms()
        traefik_vm = vms.get_traefik_vm()
        if traefik_vm is None:
            raise ValueError("No Traefik VM configured. Add a VM with role 'traefik'.")
        return traefik_vm

    def _generate_static_config(self, settings: Settings) -> str:
        """Generate Traefik static configuration."""
        config = {
            "api": {
                "dashboard": settings.traefik.dashboard_enabled,
                "insecure": False
            },
            "entryPoints": {
                "web": {
                    "address": ":80",
                    "http": {
                        "redirections": {
                            "entryPoint": {
                                "to": "websecure",
                                "scheme": "https"
                            }
                        }
                    }
                },
                "websecure": {
                    "address": ":443"
                }
            },
            "providers": {
                "file": {
                    "directory": TRAEFIK_DYNAMIC_PATH,
                    "watch": True
                }
            },
            "certificatesResolvers": {
                "letsencrypt": {
                    "acme": {
                        "email": settings.email,
                        "storage": f"{TRAEFIK_BASE_PATH}/acme.json",
                        "httpChallenge": {
                            "entryPoint": "web"
                        }
                    }
                }
            },
            "log": {
                "level": "INFO"
            },
            "accessLog": {}
        }

        # Use staging server if configured
        if settings.ssl.staging:
            config["certificatesResolvers"]["letsencrypt"]["acme"]["caServer"] = \
                "https://acme-staging-v02.api.letsencrypt.org/directory"

        return yaml.dump(config, default_flow_style=False)

    def _generate_dashboard_config(self, settings: Settings) -> str:
        """Generate Traefik dashboard dynamic configuration."""
        subdomain = settings.traefik.dashboard_subdomain
        domain = settings.domain

        config = {
            "http": {
                "routers": {
                    "dashboard": {
                        "rule": f"Host(`{subdomain}.{domain}`)",
                        "service": "api@internal",
                        "tls": {
                            "certResolver": "letsencrypt"
                        },
                        "middlewares": ["dashboard-auth"]
                    }
                },
                "middlewares": {
                    "dashboard-auth": {
                        "basicAuth": {
                            "users": [settings.traefik.dashboard_auth]
                        }
                    }
                }
            }
        }

        return yaml.dump(config, default_flow_style=False)

    def _generate_docker_compose(self) -> str:
        """Generate Traefik docker-compose.yml."""
        return f"""version: '3.8'

services:
  traefik:
    image: traefik:v3.2
    container_name: traefik
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - {TRAEFIK_BASE_PATH}/traefik.yml:/etc/traefik/traefik.yml:ro
      - {TRAEFIK_DYNAMIC_PATH}:/etc/traefik/dynamic:ro
      - {TRAEFIK_BASE_PATH}/acme.json:/acme.json
    networks:
      - traefik-public

networks:
  traefik-public:
    external: true
"""

    def generate_service_config(self, route: ServiceRoute, settings: Settings) -> str:
        """Generate dynamic configuration for a service route."""
        domain = settings.domain

        config = {
            "http": {
                "routers": {
                    route.name: {
                        "rule": f"Host(`{route.subdomain}.{domain}`)",
                        "service": route.name,
                    }
                },
                "services": {
                    route.name: {
                        "loadBalancer": {
                            "servers": [
                                {"url": f"http://{route.target_host}:{route.target_port}"}
                            ]
                        }
                    }
                }
            }
        }

        # Add TLS configuration
        if route.https:
            config["http"]["routers"][route.name]["tls"] = {
                "certResolver": "letsencrypt"
            }
            config["http"]["routers"][route.name]["entryPoints"] = ["websecure"]
        else:
            config["http"]["routers"][route.name]["entryPoints"] = ["web"]

        # Add middlewares if specified
        if route.middlewares:
            config["http"]["routers"][route.name]["middlewares"] = route.middlewares

        return yaml.dump(config, default_flow_style=False)

    def deploy_traefik(self) -> tuple[bool, str]:
        """Deploy Traefik on the Traefik VM."""
        try:
            vm = self._get_traefik_vm()
            settings = self.config_loader.load_settings()

            # Create directories
            self.ssh.run_command(vm, f"mkdir -p {TRAEFIK_BASE_PATH} {TRAEFIK_DYNAMIC_PATH}")

            # Create network if not exists
            self.ssh.run_command(
                vm,
                "docker network create traefik-public 2>/dev/null || true"
            )

            # Create acme.json with correct permissions
            self.ssh.run_command(
                vm,
                f"touch {TRAEFIK_BASE_PATH}/acme.json && chmod 600 {TRAEFIK_BASE_PATH}/acme.json"
            )

            # Upload static config
            static_config = self._generate_static_config(settings)
            self.ssh.upload_content(vm, static_config, f"{TRAEFIK_BASE_PATH}/traefik.yml")

            # Upload dashboard config
            if settings.traefik.dashboard_enabled and settings.traefik.dashboard_auth:
                dashboard_config = self._generate_dashboard_config(settings)
                self.ssh.upload_content(
                    vm,
                    dashboard_config,
                    f"{TRAEFIK_DYNAMIC_PATH}/dashboard.yml"
                )

            # Upload docker-compose
            compose = self._generate_docker_compose()
            self.ssh.upload_content(vm, compose, f"{TRAEFIK_BASE_PATH}/docker-compose.yml")

            # Start Traefik
            success, output = self.docker.compose_up(vm, TRAEFIK_BASE_PATH)
            if success:
                return True, "Traefik deployed successfully"
            return False, output

        except Exception as e:
            return False, str(e)

    def add_service_route(self, route: ServiceRoute) -> tuple[bool, str]:
        """Add a service route to Traefik configuration."""
        try:
            vm = self._get_traefik_vm()
            settings = self.config_loader.load_settings()

            # Generate and upload config
            config = self.generate_service_config(route, settings)
            config_path = f"{TRAEFIK_DYNAMIC_PATH}/{route.name}.yml"
            self.ssh.upload_content(vm, config, config_path)

            return True, f"Route added: {route.subdomain}.{settings.domain}"

        except Exception as e:
            return False, str(e)

    def remove_service_route(self, service_name: str) -> tuple[bool, str]:
        """Remove a service route from Traefik configuration."""
        try:
            vm = self._get_traefik_vm()
            config_path = f"{TRAEFIK_DYNAMIC_PATH}/{service_name}.yml"

            result = self.ssh.run_command(vm, f"rm -f {config_path}")
            if result.success:
                return True, f"Route removed: {service_name}"
            return False, result.stderr

        except Exception as e:
            return False, str(e)

    def list_routes(self) -> list[str]:
        """List all configured service routes."""
        try:
            vm = self._get_traefik_vm()
            result = self.ssh.run_command(vm, f"ls -1 {TRAEFIK_DYNAMIC_PATH}/*.yml 2>/dev/null")

            if result.success and result.stdout:
                routes = []
                for line in result.stdout.split('\n'):
                    if line.strip():
                        # Extract service name from path
                        name = line.split('/')[-1].replace('.yml', '')
                        if name != 'dashboard':  # Exclude dashboard
                            routes.append(name)
                return routes
            return []

        except Exception:
            return []

    def get_traefik_status(self) -> tuple[bool, str]:
        """Get Traefik container status."""
        try:
            vm = self._get_traefik_vm()
            containers = self.docker.compose_ps(vm, TRAEFIK_BASE_PATH)

            if not containers:
                return False, "Traefik not deployed"

            traefik = next((c for c in containers if c.name == "traefik"), None)
            if traefik and traefik.running:
                return True, f"Running: {traefik.status}"
            return False, f"Not running: {traefik.status if traefik else 'Container not found'}"

        except Exception as e:
            return False, str(e)

    def restart_traefik(self) -> tuple[bool, str]:
        """Restart Traefik container."""
        try:
            vm = self._get_traefik_vm()
            return self.docker.restart_container(vm, "traefik")
        except Exception as e:
            return False, str(e)

    def get_traefik_logs(self, tail: int = 100) -> str:
        """Get Traefik logs."""
        try:
            vm = self._get_traefik_vm()
            return self.docker.get_container_logs(vm, "traefik", tail)
        except Exception as e:
            return str(e)


# Global Traefik manager instance
_traefik_manager: Optional[TraefikManager] = None


def get_traefik_manager() -> TraefikManager:
    """Get or create the global Traefik manager instance."""
    global _traefik_manager
    if _traefik_manager is None:
        _traefik_manager = TraefikManager()
    return _traefik_manager
