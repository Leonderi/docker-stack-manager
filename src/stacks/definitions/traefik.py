"""Traefik reverse proxy stack definition."""

from ..base import BaseStack, StackConfig, StackInfo, register_stack
from ...core.config_loader import VMConfig, get_config_loader
from ...core.traefik_manager import get_traefik_manager


@register_stack
class TraefikStack(BaseStack):
    """Traefik reverse proxy stack."""

    @property
    def info(self) -> StackInfo:
        return StackInfo(
            name="traefik",
            display_name="Traefik (Reverse Proxy)",
            description="Reverse proxy with automatic SSL certificates. Deploy on Traefik VM only.",
            default_port=443,
            required_env_vars=[],
            optional_env_vars={},
        )

    def generate_compose(self, config: StackConfig) -> str:
        """Traefik uses its own compose generation via TraefikManager."""
        return ""

    def validate_config(self, config: StackConfig) -> tuple[bool, str]:
        """Validate Traefik configuration."""
        # Traefik doesn't need subdomain or env vars
        return True, "Configuration valid"

    def deploy(
        self,
        vm: VMConfig,
        config: StackConfig
    ) -> tuple[bool, str]:
        """Deploy Traefik to the VM."""
        # Verify this is a Traefik VM
        if vm.role != "traefik":
            return False, "Traefik can only be deployed on VMs with role 'traefik'"

        # Use TraefikManager for deployment
        traefik_manager = get_traefik_manager()
        success, message = traefik_manager.deploy_traefik()

        if success:
            # Update VM stacks in config
            config_loader = get_config_loader()
            vms = config_loader.load_vms()
            for v in vms.vms:
                if v.name == vm.name:
                    if self.info.name not in v.stacks:
                        v.stacks.append(self.info.name)
                    break
            config_loader.save_vms(vms)

            settings = config_loader.load_settings()
            dashboard_url = f"https://{settings.traefik.dashboard_subdomain}.{settings.domain}"
            return True, f"Traefik deployed! Dashboard: {dashboard_url}"

        return False, message

    def undeploy(self, vm: VMConfig, remove_data: bool = False) -> tuple[bool, str]:
        """Remove Traefik from the VM."""
        try:
            # Stop Traefik containers
            success, output = self.docker.compose_down(vm, "/opt/traefik", remove_volumes=remove_data)

            if remove_data:
                self.ssh.run_command(vm, "rm -rf /opt/traefik")

            # Update VM stacks in config
            config_loader = get_config_loader()
            vms = config_loader.load_vms()
            for v in vms.vms:
                if v.name == vm.name:
                    if self.info.name in v.stacks:
                        v.stacks.remove(self.info.name)
                    break
            config_loader.save_vms(vms)

            return True, "Traefik removed successfully"

        except Exception as e:
            return False, str(e)

    def get_status(self, vm: VMConfig) -> tuple[bool, str]:
        """Get Traefik status."""
        traefik_manager = get_traefik_manager()
        return traefik_manager.get_traefik_status()
