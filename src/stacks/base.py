"""Base stack class and stack registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..core.config_loader import VMConfig, Settings, get_config_loader
from ..core.docker_manager import DockerManager, get_docker_manager
from ..core.ssh_manager import SSHManager, get_ssh_manager
from ..core.traefik_manager import TraefikManager, ServiceRoute, get_traefik_manager


STACKS_BASE_PATH = "/opt/stacks"


@dataclass
class StackConfig:
    """Configuration for a stack deployment."""
    subdomain: str
    env_vars: dict[str, str] = field(default_factory=dict)
    volumes: dict[str, str] = field(default_factory=dict)
    port: int = 0  # Internal port for Traefik routing


@dataclass
class StackInfo:
    """Information about a stack."""
    name: str
    display_name: str
    description: str
    default_port: int
    required_env_vars: list[str]
    optional_env_vars: dict[str, str]  # name -> default value
    dependencies: list[str] = field(default_factory=list)


class BaseStack(ABC):
    """Base class for all stack definitions."""

    def __init__(
        self,
        ssh_manager: Optional[SSHManager] = None,
        docker_manager: Optional[DockerManager] = None,
        traefik_manager: Optional[TraefikManager] = None
    ):
        """Initialize base stack."""
        self.ssh = ssh_manager or get_ssh_manager()
        self.docker = docker_manager or get_docker_manager()
        self.traefik = traefik_manager or get_traefik_manager()
        self.config_loader = get_config_loader()

    @property
    @abstractmethod
    def info(self) -> StackInfo:
        """Return stack information."""
        pass

    @abstractmethod
    def generate_compose(self, config: StackConfig) -> str:
        """Generate docker-compose.yml content."""
        pass

    def get_stack_path(self, vm: VMConfig) -> str:
        """Get the path where this stack will be deployed."""
        return f"{STACKS_BASE_PATH}/{self.info.name}"

    def validate_config(self, config: StackConfig) -> tuple[bool, str]:
        """Validate stack configuration."""
        missing = []
        for var in self.info.required_env_vars:
            if var not in config.env_vars or not config.env_vars[var]:
                missing.append(var)

        if missing:
            return False, f"Missing required environment variables: {', '.join(missing)}"

        if not config.subdomain:
            return False, "Subdomain is required"

        return True, "Configuration valid"

    def deploy(
        self,
        vm: VMConfig,
        config: StackConfig
    ) -> tuple[bool, str]:
        """Deploy the stack to a VM."""
        # Validate configuration
        valid, msg = self.validate_config(config)
        if not valid:
            return False, msg

        stack_path = self.get_stack_path(vm)

        try:
            # Create stack directory
            self.ssh.mkdir(vm, stack_path)

            # Fill in optional env vars with defaults
            for var, default in self.info.optional_env_vars.items():
                if var not in config.env_vars:
                    config.env_vars[var] = default

            # Set port if not specified
            if config.port == 0:
                config.port = self.info.default_port

            # Generate and upload docker-compose
            compose_content = self.generate_compose(config)
            compose_path = f"{stack_path}/docker-compose.yml"
            self.ssh.upload_content(vm, compose_content, compose_path)

            # Generate .env file if there are env vars
            if config.env_vars:
                env_content = "\n".join(f"{k}={v}" for k, v in config.env_vars.items())
                env_path = f"{stack_path}/.env"
                self.ssh.upload_content(vm, env_content, env_path)

            # Pull images
            self.docker.compose_pull(vm, stack_path)

            # Start stack
            success, output = self.docker.compose_up(vm, stack_path)
            if not success:
                return False, f"Failed to start stack: {output}"

            # Add Traefik route
            settings = self.config_loader.load_settings()
            route = ServiceRoute(
                name=self.info.name,
                subdomain=config.subdomain,
                target_host=vm.host,
                target_port=config.port
            )
            route_success, route_msg = self.traefik.add_service_route(route)
            if not route_success:
                return False, f"Stack started but Traefik route failed: {route_msg}"

            # Update VM stacks in config
            vms = self.config_loader.load_vms()
            for v in vms.vms:
                if v.name == vm.name:
                    if self.info.name not in v.stacks:
                        v.stacks.append(self.info.name)
                    break
            self.config_loader.save_vms(vms)

            return True, f"Stack deployed: {config.subdomain}.{settings.domain}"

        except Exception as e:
            return False, str(e)

    def undeploy(self, vm: VMConfig, remove_data: bool = False) -> tuple[bool, str]:
        """Remove the stack from a VM."""
        stack_path = self.get_stack_path(vm)

        try:
            # Stop and remove containers
            success, output = self.docker.compose_down(vm, stack_path, remove_volumes=remove_data)

            # Remove Traefik route
            self.traefik.remove_service_route(self.info.name)

            # Remove stack directory if removing data
            if remove_data:
                self.ssh.run_command(vm, f"rm -rf {stack_path}")

            # Update VM stacks in config
            vms = self.config_loader.load_vms()
            for v in vms.vms:
                if v.name == vm.name:
                    if self.info.name in v.stacks:
                        v.stacks.remove(self.info.name)
                    break
            self.config_loader.save_vms(vms)

            return True, "Stack removed successfully"

        except Exception as e:
            return False, str(e)

    def get_status(self, vm: VMConfig) -> tuple[bool, str]:
        """Get stack status on a VM."""
        stack_path = self.get_stack_path(vm)

        try:
            containers = self.docker.compose_ps(vm, stack_path)
            if not containers:
                return False, "Not deployed"

            running = all(c.running for c in containers)
            status_str = ", ".join(f"{c.name}: {c.status}" for c in containers)

            return running, status_str

        except Exception as e:
            return False, str(e)

    def get_logs(self, vm: VMConfig, tail: int = 100) -> str:
        """Get stack logs."""
        stack_path = self.get_stack_path(vm)
        return self.docker.compose_logs(vm, stack_path, tail)

    def restart(self, vm: VMConfig) -> tuple[bool, str]:
        """Restart the stack."""
        stack_path = self.get_stack_path(vm)

        try:
            # Stop
            self.docker.compose_down(vm, stack_path)
            # Start
            success, output = self.docker.compose_up(vm, stack_path)
            if success:
                return True, "Stack restarted"
            return False, output

        except Exception as e:
            return False, str(e)


# Stack registry
_stack_registry: dict[str, type[BaseStack]] = {}


def register_stack(stack_class: type[BaseStack]) -> type[BaseStack]:
    """Decorator to register a stack class."""
    # Create temporary instance to get info
    instance = stack_class()
    _stack_registry[instance.info.name] = stack_class
    return stack_class


def get_available_stacks() -> dict[str, StackInfo]:
    """Get all available stacks."""
    return {name: cls().info for name, cls in _stack_registry.items()}


def get_stack(name: str) -> Optional[BaseStack]:
    """Get a stack instance by name."""
    if name in _stack_registry:
        return _stack_registry[name]()
    return None


def get_stack_class(name: str) -> Optional[type[BaseStack]]:
    """Get a stack class by name."""
    return _stack_registry.get(name)
