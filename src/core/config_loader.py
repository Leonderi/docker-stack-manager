"""Configuration loader for settings and VM definitions."""

import ipaddress
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class TraefikConfig(BaseModel):
    """Traefik-specific configuration."""
    dashboard_enabled: bool = True
    dashboard_subdomain: str = "traefik"
    dashboard_access: str = "local"  # "local" (no auth) or "public" (with auth via domain)
    dashboard_username: str = "admin"
    dashboard_password: str = ""  # Plain text, will be hashed for htpasswd
    dashboard_auth: str = ""  # Legacy htpasswd format, kept for compatibility


class SSLConfig(BaseModel):
    """SSL/TLS configuration."""
    provider: str = "letsencrypt"
    staging: bool = True
    challenge_type: str = "http"  # "http" or "dns"
    dns_provider: str = ""  # cloudflare, route53, etc.
    dns_api_key: str = ""
    dns_api_secret: str = ""


class OPNsenseConfig(BaseModel):
    """OPNsense firewall configuration."""
    enabled: bool = False
    host: str = ""
    api_key: str = ""
    api_secret: str = ""
    wan_interface: str = "wan"
    lan_interface: str = "lan"


class ProxmoxConfig(BaseModel):
    """Proxmox VE configuration."""
    enabled: bool = False
    host: str = ""
    port: int = 8006
    user: str = "root@pam"
    token_name: str = ""
    token_value: str = ""
    verify_ssl: bool = False
    default_node: str = ""
    default_storage: str = "local-lvm"
    template_storage: str = "local"
    default_template: str = ""
    default_bridge: str = "vmbr0"


class LXCDefaults(BaseModel):
    """Default settings for LXC container creation."""
    memory: int = 512  # MB
    swap: int = 512  # MB
    cores: int = 1
    rootfs_size: int = 8  # GB
    unprivileged: bool = True
    start_on_boot: bool = True
    start_after_create: bool = True
    features: str = "nesting=1"  # Enable nesting for Docker support


class InfraNetworkConfig(BaseModel):
    """Infrastructure network configuration."""
    subnet: str = "192.168.1.0/24"
    gateway: str = "192.168.1.1"
    dns_primary: str = "192.168.1.1"
    dns_secondary: str = "8.8.8.8"
    domain_suffix: str = "local"
    proxy_network: str = "traefik-public"

    @field_validator('subnet')
    @classmethod
    def validate_subnet(cls, v):
        """Validate subnet is a valid CIDR notation."""
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid subnet: {e}")
        return v

    @field_validator('gateway', 'dns_primary', 'dns_secondary')
    @classmethod
    def validate_ip(cls, v):
        """Validate IP address."""
        if v:
            try:
                ipaddress.ip_address(v)
            except ValueError as e:
                raise ValueError(f"Invalid IP address: {e}")
        return v

    def get_network(self) -> ipaddress.IPv4Network:
        """Get the network object."""
        return ipaddress.ip_network(self.subnet, strict=False)

    def is_ip_in_subnet(self, ip: str) -> bool:
        """Check if an IP is within the configured subnet."""
        try:
            return ipaddress.ip_address(ip) in self.get_network()
        except ValueError:
            return False

    def get_available_ips(self, used_ips: list[str]) -> list[str]:
        """Get list of available IPs in the subnet."""
        network = self.get_network()
        used = set(used_ips)
        used.add(self.gateway)  # Gateway is always used

        available = []
        for host in network.hosts():
            ip = str(host)
            if ip not in used:
                available.append(ip)

        return available[:50]  # Return max 50 for UI performance


class Settings(BaseModel):
    """Global application settings."""
    domain: str = ""
    email: str = ""
    traefik: TraefikConfig = Field(default_factory=TraefikConfig)
    ssl: SSLConfig = Field(default_factory=SSLConfig)
    network: InfraNetworkConfig = Field(default_factory=InfraNetworkConfig)
    opnsense: OPNsenseConfig = Field(default_factory=OPNsenseConfig)
    proxmox: ProxmoxConfig = Field(default_factory=ProxmoxConfig)
    lxc_defaults: LXCDefaults = Field(default_factory=LXCDefaults)
    first_run_complete: bool = False


class VMNetworkConfig(BaseModel):
    """Network configuration for a VM."""
    ip_address: str = ""
    netmask: str = "255.255.255.0"
    gateway: str = ""
    dns_primary: str = ""
    dns_secondary: str = ""
    mac_address: str = ""

    @field_validator('ip_address', 'gateway', 'dns_primary', 'dns_secondary')
    @classmethod
    def validate_ip(cls, v):
        """Validate IP address (allow empty)."""
        if v:
            try:
                ipaddress.ip_address(v)
            except ValueError as e:
                raise ValueError(f"Invalid IP address: {e}")
        return v


class VMConfig(BaseModel):
    """Virtual machine configuration."""
    name: str
    host: str  # Can be IP or hostname for SSH connection
    user: str = "manager"  # Default user after initialization
    ssh_key: str = ""  # Path to private SSH key
    ssh_port: int = 22
    role: str = "worker"  # "traefik", "worker", or "manager"
    description: str = ""
    stacks: list[str] = Field(default_factory=list)
    network: VMNetworkConfig = Field(default_factory=VMNetworkConfig)

    # Proxmox Integration
    proxmox_vmid: int = 0
    proxmox_type: str = ""  # "lxc", "qemu", or "external"
    proxmox_node: str = ""

    # Initialization Status
    initialized: bool = False  # True after setup script completed

    @property
    def ssh_key_path(self) -> Path:
        """Return expanded SSH key path."""
        if self.ssh_key:
            return Path(self.ssh_key).expanduser()
        return Path()

    @property
    def display_ip(self) -> str:
        """Get the display IP (network config or host)."""
        return self.network.ip_address or self.host


class VMsConfig(BaseModel):
    """Container for all VM configurations."""
    vms: list[VMConfig] = Field(default_factory=list)

    def get_traefik_vm(self) -> Optional[VMConfig]:
        """Get the Traefik VM configuration."""
        for vm in self.vms:
            if vm.role == "traefik":
                return vm
        return None

    def get_worker_vms(self) -> list[VMConfig]:
        """Get all worker VM configurations."""
        return [vm for vm in self.vms if vm.role == "worker"]

    def get_vm_by_name(self, name: str) -> Optional[VMConfig]:
        """Get VM by name."""
        for vm in self.vms:
            if vm.name == name:
                return vm
        return None

    def get_used_ips(self) -> list[str]:
        """Get list of all used IP addresses."""
        ips = []
        for vm in self.vms:
            if vm.network.ip_address:
                ips.append(vm.network.ip_address)
            elif vm.host:
                try:
                    ipaddress.ip_address(vm.host)
                    ips.append(vm.host)
                except ValueError:
                    pass  # host is a hostname, not IP
        return ips

    def is_ip_used(self, ip: str, exclude_vm: str = None) -> bool:
        """Check if an IP is already used by another VM."""
        for vm in self.vms:
            if exclude_vm and vm.name == exclude_vm:
                continue
            if vm.network.ip_address == ip or vm.host == ip:
                return True
        return False


class ConfigLoader:
    """Loads and manages configuration files."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize config loader with config directory."""
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_dir = Path(config_dir)
        self._settings: Optional[Settings] = None
        self._vms: Optional[VMsConfig] = None
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Ensure config directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load_yaml(self, filename: str) -> dict:
        """Load a YAML file from the config directory."""
        filepath = self.config_dir / filename
        if not filepath.exists():
            return {}

        with open(filepath) as f:
            return yaml.safe_load(f) or {}

    def _save_yaml(self, filename: str, data: dict) -> None:
        """Save data to a YAML file in the config directory."""
        filepath = self.config_dir / filename
        with open(filepath, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    def config_exists(self) -> bool:
        """Check if configuration files exist."""
        settings_file = self.config_dir / "settings.yaml"
        return settings_file.exists()

    def is_first_run(self) -> bool:
        """Check if this is the first run."""
        if not self.config_exists():
            return True
        try:
            settings = self.load_settings()
            return not settings.first_run_complete
        except Exception:
            return True

    def load_settings(self, reload: bool = False) -> Settings:
        """Load global settings."""
        if self._settings is None or reload:
            data = self._load_yaml("settings.yaml")
            self._settings = Settings(**data)
        return self._settings

    def save_settings(self, settings: Settings) -> None:
        """Save global settings."""
        data = settings.model_dump()
        self._save_yaml("settings.yaml", data)
        self._settings = settings

    def update_settings(self, **kwargs) -> Settings:
        """Update specific settings fields."""
        settings = self.load_settings()
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        self.save_settings(settings)
        return settings

    def load_vms(self, reload: bool = False) -> VMsConfig:
        """Load VM configurations."""
        if self._vms is None or reload:
            data = self._load_yaml("vms.yaml")
            self._vms = VMsConfig(**data)
        return self._vms

    def save_vms(self, vms_config: VMsConfig) -> None:
        """Save VM configurations."""
        data = {"vms": [vm.model_dump() for vm in vms_config.vms]}
        self._save_yaml("vms.yaml", data)
        self._vms = vms_config

    def add_vm(self, vm: VMConfig) -> None:
        """Add a new VM to the configuration."""
        vms = self.load_vms()
        vms.vms.append(vm)
        self.save_vms(vms)

    def update_vm(self, vm_name: str, updated_vm: VMConfig) -> bool:
        """Update an existing VM configuration."""
        vms = self.load_vms()
        for i, vm in enumerate(vms.vms):
            if vm.name == vm_name:
                vms.vms[i] = updated_vm
                self.save_vms(vms)
                return True
        return False

    def remove_vm(self, name: str) -> bool:
        """Remove a VM from the configuration."""
        vms = self.load_vms()
        original_count = len(vms.vms)
        vms.vms = [vm for vm in vms.vms if vm.name != name]
        if len(vms.vms) < original_count:
            self.save_vms(vms)
            return True
        return False

    def update_vm_stacks(self, vm_name: str, stacks: list[str]) -> None:
        """Update the deployed stacks for a VM."""
        vms = self.load_vms()
        for vm in vms.vms:
            if vm.name == vm_name:
                vm.stacks = stacks
                break
        self.save_vms(vms)

    def update_vm_network(self, vm_name: str, network: VMNetworkConfig) -> bool:
        """Update network configuration for a VM."""
        vms = self.load_vms()
        for vm in vms.vms:
            if vm.name == vm_name:
                vm.network = network
                # Also update host if IP is set
                if network.ip_address:
                    vm.host = network.ip_address
                self.save_vms(vms)
                return True
        return False

    def get_available_ips(self) -> list[str]:
        """Get available IPs based on network config and used IPs."""
        settings = self.load_settings()
        vms = self.load_vms()
        used_ips = vms.get_used_ips()
        return settings.network.get_available_ips(used_ips)

    def complete_first_run(self) -> None:
        """Mark first run as complete."""
        settings = self.load_settings()
        settings.first_run_complete = True
        self.save_settings(settings)


# Global config loader instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader(config_dir: Optional[Path] = None) -> ConfigLoader:
    """Get or create the global config loader instance."""
    global _config_loader
    if _config_loader is None or config_dir is not None:
        _config_loader = ConfigLoader(config_dir)
    return _config_loader
