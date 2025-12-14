"""LXC Container Manager - orchestrates Proxmox LXC container creation."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config_loader import (
    ConfigLoader,
    LXCDefaults,
    ProxmoxConfig,
    Settings,
    VMConfig,
    VMNetworkConfig,
    get_config_loader,
)
from .proxmox_api import ProxmoxAPI, ProxmoxAPIError, get_proxmox_api
from .ssh_keygen import SSHKeyManager, get_ssh_key_manager


@dataclass
class LXCCreationResult:
    """Result of LXC container creation."""
    success: bool
    vmid: int = 0
    hostname: str = ""
    ip_address: str = ""
    ssh_key_path: str = ""
    message: str = ""
    error: str = ""


@dataclass
class LXCCreationConfig:
    """Configuration for creating an LXC container."""
    hostname: str
    ip_address: str
    gateway: str = ""
    dns_primary: str = ""
    dns_secondary: str = ""
    netmask: str = "24"  # CIDR prefix
    memory: int = 0  # 0 = use default
    swap: int = 0
    cores: int = 0
    rootfs_size: int = 0
    role: str = "worker"
    description: str = ""
    template: str = ""  # Empty = use default
    node: str = ""  # Empty = use default
    bridge: str = ""  # Empty = use default
    vmid: int = 0  # 0 = auto-assign


class LXCManager:
    """Manages LXC container lifecycle through Proxmox API."""

    def __init__(
        self,
        config_loader: ConfigLoader = None,
        ssh_key_manager: SSHKeyManager = None,
    ):
        """Initialize LXC Manager."""
        self.config_loader = config_loader or get_config_loader()
        self.ssh_key_manager = ssh_key_manager or get_ssh_key_manager()
        self._api: Optional[ProxmoxAPI] = None

    def _get_api(self) -> ProxmoxAPI:
        """Get configured Proxmox API client."""
        if self._api is None:
            settings = self.config_loader.load_settings()
            pve = settings.proxmox

            if not pve.enabled:
                raise ProxmoxAPIError("Proxmox integration is not enabled")
            if not pve.host or not pve.token_name or not pve.token_value:
                raise ProxmoxAPIError("Proxmox configuration is incomplete")

            self._api = ProxmoxAPI(
                host=pve.host,
                user=pve.user,
                token_name=pve.token_name,
                token_value=pve.token_value,
                port=pve.port,
                verify_ssl=pve.verify_ssl,
            )

        return self._api

    def test_connection(self) -> tuple[bool, str]:
        """Test Proxmox API connection."""
        try:
            api = self._get_api()
            return api.test_connection()
        except ProxmoxAPIError as e:
            return False, str(e)

    def get_nodes(self) -> list[dict]:
        """Get available Proxmox nodes."""
        api = self._get_api()
        return api.get_nodes()

    def get_templates(self, node: str = None, storage: str = None) -> list[dict]:
        """Get available LXC templates."""
        settings = self.config_loader.load_settings()
        api = self._get_api()

        node = node or settings.proxmox.default_node
        storage = storage or settings.proxmox.template_storage

        if not node:
            nodes = api.get_nodes()
            if nodes:
                node = nodes[0]["node"]

        return api.get_lxc_templates(node, storage)

    def get_storage_list(self, node: str = None) -> list[dict]:
        """Get available storage on a node."""
        settings = self.config_loader.load_settings()
        api = self._get_api()

        node = node or settings.proxmox.default_node
        if not node:
            nodes = api.get_nodes()
            if nodes:
                node = nodes[0]["node"]

        return api.get_storage_list(node)

    def get_next_vmid(self) -> int:
        """Get the next available VMID."""
        api = self._get_api()
        return api.get_next_vmid()

    def is_vmid_available(self, vmid: int) -> bool:
        """Check if a VMID is available."""
        api = self._get_api()
        return api.is_vmid_available(vmid)

    def get_containers(self, node: str = None) -> list[dict]:
        """Get all LXC containers on a node."""
        settings = self.config_loader.load_settings()
        api = self._get_api()

        node = node or settings.proxmox.default_node
        if not node:
            nodes = api.get_nodes()
            if nodes:
                node = nodes[0]["node"]

        return api.get_lxc_containers(node)

    def create_container(
        self,
        config: LXCCreationConfig,
        progress_callback: Callable[[str], None] = None,
    ) -> LXCCreationResult:
        """
        Create a new LXC container with auto-generated SSH key.

        Args:
            config: Container configuration
            progress_callback: Optional callback for progress updates

        Returns:
            LXCCreationResult with creation status
        """
        def log(msg: str):
            if progress_callback:
                progress_callback(msg)

        try:
            settings = self.config_loader.load_settings()
            pve = settings.proxmox
            defaults = settings.lxc_defaults
            api = self._get_api()

            # Determine node
            node = config.node or pve.default_node
            if not node:
                nodes = api.get_nodes()
                if not nodes:
                    return LXCCreationResult(
                        success=False,
                        error="No Proxmox nodes available"
                    )
                node = nodes[0]["node"]

            log(f"Using node: {node}")

            # Get or validate VMID
            if config.vmid > 0:
                # Use provided VMID if available
                if not api.is_vmid_available(config.vmid):
                    return LXCCreationResult(
                        success=False,
                        error=f"VMID {config.vmid} is already in use"
                    )
                vmid = config.vmid
                log(f"Using provided VMID: {vmid}")
            else:
                # Auto-assign next available VMID
                vmid = api.get_next_vmid()
                log(f"Allocated VMID: {vmid}")

            # Generate SSH keypair for root access (temporary, until initialization)
            key_name = f"{config.hostname}_root"
            log(f"Generating root SSH keypair: {key_name}")
            private_key_path, public_key_path, public_key = self.ssh_key_manager.get_or_create_keypair(
                key_name,
                comment=f"root@{config.hostname}"
            )
            log(f"SSH key saved to: {private_key_path}")

            # Determine template
            template = config.template or pve.default_template
            if not template:
                # Try to find a Debian template
                templates = self.get_templates(node, pve.template_storage)
                for t in templates:
                    if "debian" in t.get("volid", "").lower():
                        template = t["volid"]
                        break
                if not template and templates:
                    template = templates[0]["volid"]

            if not template:
                return LXCCreationResult(
                    success=False,
                    error="No LXC template available. Please download one first."
                )

            # Ensure template has storage prefix
            if ":" not in template:
                template = f"{pve.template_storage}:vztmpl/{template}"

            log(f"Using template: {template}")

            # Build network configuration
            bridge = config.bridge or pve.default_bridge
            gateway = config.gateway or settings.network.gateway
            dns1 = config.dns_primary or settings.network.dns_primary
            dns2 = config.dns_secondary or settings.network.dns_secondary

            netmask = config.netmask if config.netmask else "24"
            net0 = f"name=eth0,bridge={bridge},ip={config.ip_address}/{netmask},gw={gateway}"

            nameserver = dns1
            if dns2:
                nameserver = f"{dns1} {dns2}"

            log(f"Network: {config.ip_address}/{netmask}, GW: {gateway}")

            # Get container settings
            memory = config.memory or defaults.memory
            swap = config.swap or defaults.swap
            cores = config.cores or defaults.cores
            rootfs_size = config.rootfs_size or defaults.rootfs_size
            storage = pve.default_storage

            log(f"Resources: {memory}MB RAM, {cores} cores, {rootfs_size}GB disk")

            # Create container
            log("Creating LXC container...")
            upid = api.create_lxc(
                node=node,
                vmid=vmid,
                hostname=config.hostname,
                ostemplate=template,
                storage=storage,
                rootfs_size=rootfs_size,
                memory=memory,
                swap=swap,
                cores=cores,
                ssh_public_keys=public_key,
                net0=net0,
                nameserver=nameserver,
                searchdomain=settings.network.domain_suffix,
                start_after_create=defaults.start_after_create,
                unprivileged=defaults.unprivileged,
                features=defaults.features,
                onboot=defaults.start_on_boot,
                description=config.description or f"Created by Docker Stack Manager\nRole: {config.role}",
            )

            # Wait for creation task
            log("Waiting for container creation...")
            api.wait_for_task(node, upid, timeout=300)
            log("Container created successfully!")

            # Add VM to configuration
            log("Adding container to configuration...")
            vm_config = VMConfig(
                name=config.hostname,
                host=config.ip_address,
                user="root",  # Will be changed to "manager" after initialization
                ssh_key=str(private_key_path),
                ssh_port=22,
                role=config.role,
                description=config.description,
                network=VMNetworkConfig(
                    ip_address=config.ip_address,
                    netmask=self._cidr_to_netmask(int(netmask)),
                    gateway=gateway,
                    dns_primary=dns1,
                    dns_secondary=dns2,
                ),
                proxmox_vmid=vmid,
                proxmox_type="lxc",
                proxmox_node=node,
                initialized=False,  # Must run Initialize to set up manager user
            )
            self.config_loader.add_vm(vm_config)

            log("Container ready!")

            return LXCCreationResult(
                success=True,
                vmid=vmid,
                hostname=config.hostname,
                ip_address=config.ip_address,
                ssh_key_path=str(private_key_path),
                message=f"Container {config.hostname} (VMID {vmid}) created successfully",
            )

        except ProxmoxAPIError as e:
            return LXCCreationResult(
                success=False,
                error=f"Proxmox API error: {e.message}",
            )
        except Exception as e:
            return LXCCreationResult(
                success=False,
                error=f"Error: {str(e)}",
            )

    def start_container(self, vmid: int, node: str = None) -> tuple[bool, str]:
        """Start an LXC container."""
        try:
            settings = self.config_loader.load_settings()
            api = self._get_api()
            node = node or settings.proxmox.default_node

            api.start_lxc(node, vmid)
            return True, f"Container {vmid} started"
        except ProxmoxAPIError as e:
            return False, str(e)

    def stop_container(self, vmid: int, node: str = None) -> tuple[bool, str]:
        """Stop an LXC container."""
        try:
            settings = self.config_loader.load_settings()
            api = self._get_api()
            node = node or settings.proxmox.default_node

            api.stop_lxc(node, vmid)
            return True, f"Container {vmid} stopped"
        except ProxmoxAPIError as e:
            return False, str(e)

    def delete_container(
        self,
        vmid: int,
        node: str = None,
        delete_ssh_key: bool = True,
    ) -> tuple[bool, str]:
        """Delete an LXC container and optionally its SSH key."""
        try:
            settings = self.config_loader.load_settings()
            api = self._get_api()
            node = node or settings.proxmox.default_node

            # Get container info to find hostname
            try:
                config = api.get_lxc_config(node, vmid)
                hostname = config.get("hostname", "")
            except Exception:
                hostname = ""

            # Stop container if running and wait for it
            try:
                status = api.get_lxc_status(node, vmid)
                if status.get("status") == "running":
                    upid = api.stop_lxc(node, vmid)
                    # Wait for stop task to complete
                    if upid:
                        try:
                            api.wait_for_task(node, upid, timeout=60)
                        except Exception:
                            pass
                    # Additional wait to ensure container is fully stopped
                    for _ in range(10):
                        time.sleep(1)
                        status = api.get_lxc_status(node, vmid)
                        if status.get("status") != "running":
                            break
            except Exception:
                pass

            # Delete container
            upid = api.delete_lxc(node, vmid)
            if upid:
                try:
                    api.wait_for_task(node, upid, timeout=120)
                except Exception:
                    pass

            # Delete SSH keys if requested (both root and manager keys)
            if delete_ssh_key and hostname:
                # Delete root key
                self.ssh_key_manager.delete_keypair(f"{hostname}_root")
                # Delete manager key (if initialized)
                self.ssh_key_manager.delete_keypair(f"{hostname}_manager")

            # Remove from config
            if hostname:
                self.config_loader.remove_vm(hostname)

            return True, f"Container {vmid} deleted"
        except ProxmoxAPIError as e:
            return False, str(e)

    def _cidr_to_netmask(self, prefix: int) -> str:
        """Convert CIDR prefix to netmask."""
        mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
        return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"


# Global instance
_lxc_manager: Optional[LXCManager] = None


def get_lxc_manager() -> LXCManager:
    """Get or create the global LXC manager instance."""
    global _lxc_manager
    if _lxc_manager is None:
        _lxc_manager = LXCManager()
    return _lxc_manager
