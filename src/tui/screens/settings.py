"""Settings screen with sidebar navigation."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Input,
    Label,
    Rule,
    Select,
    Static,
)
from textual.widgets.select import BLANK as SELECT_BLANK

from ..base_screen import BaseScreen
from ...core.config_loader import (
    get_config_loader,
    InfraNetworkConfig,
    LXCDefaults,
    OPNsenseConfig,
    ProxmoxConfig,
    Settings,
    SSLConfig,
    TraefikConfig,
)
from ...core.proxmox_api import ProxmoxAPI, ProxmoxAPIError


class SettingsScreen(BaseScreen):
    """Screen for configuring all settings with sidebar navigation."""

    CSS = """
    SettingsScreen {
        layout: vertical;
        height: 100%;
    }

    #settings-title {
        text-align: center;
        text-style: bold;
        padding: 1;
        height: auto;
    }

    #settings-main {
        height: 1fr;
    }

    #settings-sidebar {
        width: 22;
        height: 100%;
        border-right: solid $primary;
        padding: 1;
    }

    #settings-sidebar Button {
        width: 100%;
        margin-bottom: 1;
    }

    #settings-content {
        width: 1fr;
        height: 1fr;
        padding: 1;
        overflow-y: auto;
    }

    SettingsScreen VerticalScroll {
        height: 1fr;
        max-height: 100%;
    }

    .settings-section {
        display: none;
        height: auto;
    }

    .settings-section.active {
        display: block;
    }

    #status-message {
        height: auto;
        text-align: center;
        padding: 1;
    }

    .row {
        height: auto;
        width: 100%;
    }

    .row > Vertical {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }

    .subnet-row {
        height: auto;
        width: 100%;
    }

    .subnet-row > Vertical {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }

    .subnet-ip {
        width: 2fr;
    }

    .subnet-prefix {
        width: 1fr;
    }

    .subnet-netmask {
        width: 2fr;
    }

    .dns-settings {
        display: none;
        height: auto;
        margin-top: 1;
        padding: 1;
        border: solid $primary;
    }

    .dns-settings.active {
        display: block;
    }

    .auth-fields {
        height: auto;
    }

    .auth-fields.hidden {
        display: none;
    }

    Select {
        width: 100%;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def __init__(self):
        super().__init__()
        self.current_section = "ip"
        self._last_gateway = ""  # Track gateway for DNS auto-fill
        # Proxmox data
        self.nodes = []
        self.templates = []
        self.storages = []
        # Store original Proxmox select values (for when dropdowns aren't populated)
        self._original_pve_node = ""
        self._original_pve_storage = ""
        self._original_pve_template_storage = ""
        self._original_pve_template = ""

    def compose(self) -> ComposeResult:
        """Compose the settings screen."""
        yield Static("[bold]Settings[/bold]", id="settings-title")
        yield Horizontal(
            # Sidebar
            Vertical(
                Button("IP-Settings", id="btn-ip", variant="primary"),
                Button("Let's Encrypt", id="btn-ssl", variant="default"),
                Button("Traefik", id="btn-traefik", variant="default"),
                Button("Proxmox", id="btn-proxmox", variant="default"),
                Button("OPNsense", id="btn-opnsense", variant="default"),
                Rule(),
                Button("Save All", id="btn-save", variant="success"),
                Button("Back", id="btn-back", variant="default"),
                id="settings-sidebar",
            ),
            # Content area
            VerticalScroll(
                # IP Settings Section
                Vertical(
                    Static("[bold]Network Configuration[/bold]"),
                    Rule(),
                    Label("Subnet:"),
                    Horizontal(
                        Vertical(
                            Static("Network IP"),
                            Input(placeholder="192.168.1.0", id="subnet-ip"),
                            classes="subnet-ip",
                        ),
                        Vertical(
                            Static("Prefix"),
                            Input(placeholder="24", id="subnet-prefix"),
                            classes="subnet-prefix",
                        ),
                        Vertical(
                            Static("Netmask"),
                            Input(placeholder="255.255.255.0", id="subnet-netmask"),
                            classes="subnet-netmask",
                        ),
                        classes="subnet-row",
                    ),
                    Static("[dim]Gateway and DNS will auto-fill from subnet[/dim]"),
                    Label("Gateway:"),
                    Input(placeholder="192.168.1.1", id="gateway"),
                    Label("Primary DNS:"),
                    Input(placeholder="192.168.1.1", id="dns-primary"),
                    Label("Secondary DNS:"),
                    Input(placeholder="8.8.8.8", id="dns-secondary"),
                    Rule(),
                    Label("Domain Suffix:"),
                    Input(placeholder="local", id="domain-suffix"),
                    id="section-ip",
                    classes="settings-section active",
                ),
                # SSL/Let's Encrypt Section
                Vertical(
                    Static("[bold]SSL/TLS Configuration[/bold]"),
                    Rule(),
                    Label("Domain Name:"),
                    Input(placeholder="example.com", id="domain"),
                    Label("Admin Email:"),
                    Input(placeholder="admin@example.com", id="email"),
                    Label("SSL Provider:"),
                    Input(value="letsencrypt", id="ssl-provider"),
                    Checkbox("Use Staging (for testing)", id="ssl-staging"),
                    Rule(),
                    Label("Challenge Type:"),
                    Select(
                        [("HTTP-01 (Port 80)", "http"), ("DNS-01 (DNS Provider)", "dns")],
                        id="ssl-challenge",
                        value="http",
                    ),
                    Vertical(
                        Static("[bold]DNS Provider Settings[/bold]"),
                        Label("DNS Provider:"),
                        Select(
                            [
                                ("Cloudflare", "cloudflare"),
                                ("Route53 (AWS)", "route53"),
                                ("DigitalOcean", "digitalocean"),
                                ("Google Cloud DNS", "gcloud"),
                                ("Hetzner", "hetzner"),
                                ("OVH", "ovh"),
                            ],
                            id="dns-provider",
                            allow_blank=True,
                        ),
                        Label("API Key / Token:"),
                        Input(placeholder="API Key or Token", id="dns-api-key", password=True),
                        Label("API Secret (if required):"),
                        Input(placeholder="API Secret", id="dns-api-secret", password=True),
                        Static("[dim]Required credentials depend on provider[/dim]"),
                        id="dns-settings",
                        classes="dns-settings",
                    ),
                    id="section-ssl",
                    classes="settings-section",
                ),
                # Traefik Section
                Vertical(
                    Static("[bold]Traefik Configuration[/bold]"),
                    Rule(),
                    Label("Proxy Network Name:"),
                    Input(placeholder="traefik-public", id="proxy-network"),
                    Static("[dim]Docker network for container communication[/dim]"),
                    Rule(),
                    Static("[bold]Dashboard Settings[/bold]"),
                    Checkbox("Enable Dashboard", id="traefik-dashboard"),
                    Label("Dashboard Access:"),
                    Select(
                        [
                            ("Local only (no auth)", "local"),
                            ("Public via Domain (with auth)", "public"),
                        ],
                        id="traefik-access",
                        value="local",
                    ),
                    Vertical(
                        Label("Dashboard Subdomain:"),
                        Input(placeholder="traefik", id="traefik-subdomain"),
                        Label("Username:"),
                        Input(placeholder="admin", id="traefik-username", value="admin"),
                        Label("Password:"),
                        Input(placeholder="Password", id="traefik-password", password=True),
                        Static("[dim]Password will be hashed automatically[/dim]"),
                        id="traefik-auth-fields",
                        classes="auth-fields hidden",
                    ),
                    id="section-traefik",
                    classes="settings-section",
                ),
                # Proxmox Section
                Vertical(
                    Static("[bold]Proxmox VE Configuration[/bold]"),
                    Rule(),
                    Checkbox("Enable Proxmox Integration", id="pve-enabled"),
                    Horizontal(
                        Vertical(
                            Label("Proxmox Host:"),
                            Input(placeholder="192.168.1.100", id="pve-host"),
                        ),
                        Vertical(
                            Label("Port:"),
                            Input(placeholder="8006", id="pve-port", value="8006"),
                        ),
                        classes="row",
                    ),
                    Label("API User:"),
                    Input(placeholder="root@pam", id="pve-user", value="root@pam"),
                    Label("API Token Name:"),
                    Input(placeholder="docker-manager", id="pve-token-name"),
                    Label("API Token Value:"),
                    Input(placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", id="pve-token-value", password=True),
                    Checkbox("Verify SSL Certificate", id="pve-verify-ssl"),
                    Horizontal(
                        Button("Test Connection", id="btn-test-pve", variant="primary"),
                        Static("", id="pve-connection-result"),
                        classes="row",
                    ),
                    Rule(),
                    Static("[bold]Default Settings[/bold]"),
                    Label("Default Node:"),
                    Select([], id="pve-default-node", allow_blank=True),
                    Label("Storage for Containers:"),
                    Select([], id="pve-default-storage", allow_blank=True),
                    Label("Storage for Templates:"),
                    Select([], id="pve-template-storage", allow_blank=True),
                    Label("Default Network Bridge:"),
                    Input(placeholder="vmbr0", id="pve-bridge", value="vmbr0"),
                    Label("Default Template:"),
                    Select([], id="pve-default-template", allow_blank=True),
                    Rule(),
                    Static("[bold]LXC Container Defaults[/bold]"),
                    Horizontal(
                        Vertical(
                            Label("Memory (MB):"),
                            Input(placeholder="512", id="lxc-memory", value="512"),
                        ),
                        Vertical(
                            Label("Swap (MB):"),
                            Input(placeholder="512", id="lxc-swap", value="512"),
                        ),
                        classes="row",
                    ),
                    Horizontal(
                        Vertical(
                            Label("CPU Cores:"),
                            Input(placeholder="1", id="lxc-cores", value="1"),
                        ),
                        Vertical(
                            Label("Disk Size (GB):"),
                            Input(placeholder="8", id="lxc-disk", value="8"),
                        ),
                        classes="row",
                    ),
                    Checkbox("Unprivileged Container", id="lxc-unprivileged", value=True),
                    Checkbox("Start on Boot", id="lxc-onboot", value=True),
                    Checkbox("Enable Nesting (for Docker)", id="lxc-nesting", value=True),
                    id="section-proxmox",
                    classes="settings-section",
                ),
                # OPNsense Section
                Vertical(
                    Static("[bold]OPNsense Firewall[/bold]"),
                    Rule(),
                    Checkbox("Enable OPNsense Integration", id="opnsense-enabled"),
                    Label("OPNsense Host:"),
                    Input(placeholder="192.168.1.1", id="opnsense-host"),
                    Label("API Key:"),
                    Input(placeholder="API Key", id="opnsense-apikey"),
                    Label("API Secret:"),
                    Input(placeholder="API Secret", id="opnsense-apisecret", password=True),
                    Label("WAN Interface:"),
                    Input(placeholder="wan", id="opnsense-wan", value="wan"),
                    Label("LAN Interface:"),
                    Input(placeholder="lan", id="opnsense-lan", value="lan"),
                    id="section-opnsense",
                    classes="settings-section",
                ),
                id="settings-content",
            ),
            id="settings-main",
        )
        yield Static("", id="status-message")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen with current settings."""
        self.load_settings()

    def _get_select_value(self, select_id: str) -> str:
        """Get string value from Select widget, converting BLANK to empty string."""
        select = self.query_one(select_id, Select)
        value = select.value
        if value is SELECT_BLANK or value is None:
            return ""
        return str(value)

    def _get_pve_select_value(self, select_id: str, original_value: str) -> str:
        """Get value from a Proxmox Select, falling back to original if no options."""
        select = self.query_one(select_id, Select)
        # Check if select has options (beyond BLANK)
        has_options = len(select._options) > 0 if hasattr(select, '_options') else False

        if not has_options:
            # Select wasn't populated - preserve original value
            return original_value

        value = select.value
        if value is SELECT_BLANK or value is None:
            # User explicitly cleared the value
            return ""
        return str(value)

    def _update_dns_settings_visibility(self, challenge_type: str) -> None:
        """Show or hide DNS settings based on challenge type."""
        dns_settings = self.query_one("#dns-settings")
        if challenge_type == "dns":
            dns_settings.add_class("active")
        else:
            dns_settings.remove_class("active")

    def _update_auth_fields_visibility(self, access_type: str) -> None:
        """Show or hide auth fields based on access type."""
        auth_fields = self.query_one("#traefik-auth-fields")
        if access_type == "public":
            auth_fields.remove_class("hidden")
        else:
            auth_fields.add_class("hidden")

    def _calculate_gateway_from_subnet(self, subnet_ip: str, prefix: str) -> str:
        """Calculate a default gateway from subnet (usually .1 or .254)."""
        try:
            parts = subnet_ip.split(".")
            if len(parts) == 4:
                # Use .1 as default gateway (common convention)
                parts[3] = "1"
                return ".".join(parts)
        except Exception:
            pass
        return ""

    def _calculate_netmask_from_prefix(self, prefix: str) -> str:
        """Calculate netmask from CIDR prefix."""
        try:
            prefix_int = int(prefix)
            if 0 <= prefix_int <= 32:
                netmask_int = (0xFFFFFFFF << (32 - prefix_int)) & 0xFFFFFFFF
                return f"{(netmask_int >> 24) & 0xFF}.{(netmask_int >> 16) & 0xFF}.{(netmask_int >> 8) & 0xFF}.{netmask_int & 0xFF}"
        except (ValueError, TypeError):
            pass
        return "255.255.255.0"

    def _calculate_prefix_from_netmask(self, netmask: str) -> str:
        """Calculate CIDR prefix from netmask."""
        try:
            parts = netmask.split(".")
            if len(parts) == 4:
                netmask_int = (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])
                # Count the number of 1 bits
                prefix = bin(netmask_int).count("1")
                # Validate it's a valid netmask (contiguous 1s followed by 0s)
                expected = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
                if netmask_int == expected:
                    return str(prefix)
        except (ValueError, TypeError):
            pass
        return ""

    def _is_ip_in_subnet(self, ip: str, subnet_ip: str, prefix: str) -> bool:
        """Check if an IP address is within the subnet."""
        try:
            import ipaddress
            network = ipaddress.ip_network(f"{subnet_ip}/{prefix}", strict=False)
            return ipaddress.ip_address(ip) in network
        except (ValueError, TypeError):
            return False

    def _validate_ip_in_subnet(self, ip: str, field_name: str) -> bool:
        """Validate IP is in subnet and show error if not."""
        subnet_ip = self.query_one("#subnet-ip", Input).value.strip()
        prefix = self.query_one("#subnet-prefix", Input).value.strip() or "24"

        if not subnet_ip or not ip:
            return True  # Can't validate without subnet

        if not self._is_ip_in_subnet(ip, subnet_ip, prefix):
            self.show_status(f"{field_name} ({ip}) is not within subnet {subnet_ip}/{prefix}", "warning")
            return False
        return True

    def switch_section(self, section: str) -> None:
        """Switch to a different settings section."""
        self.current_section = section

        # Update button variants
        buttons = {
            "ip": "#btn-ip",
            "ssl": "#btn-ssl",
            "traefik": "#btn-traefik",
            "proxmox": "#btn-proxmox",
            "opnsense": "#btn-opnsense",
        }
        for sec, btn_id in buttons.items():
            btn = self.query_one(btn_id, Button)
            btn.variant = "primary" if sec == section else "default"

        # Show/hide sections
        sections = ["ip", "ssl", "traefik", "proxmox", "opnsense"]
        for sec in sections:
            section_widget = self.query_one(f"#section-{sec}")
            if sec == section:
                section_widget.add_class("active")
            else:
                section_widget.remove_class("active")

    def load_settings(self) -> None:
        """Load current settings into form."""
        try:
            config_loader = get_config_loader()
            settings = config_loader.load_settings(reload=True)

            # IP/Network settings - split subnet into IP and prefix
            subnet = settings.network.subnet
            if "/" in subnet:
                subnet_ip, prefix = subnet.split("/")
            else:
                subnet_ip = subnet
                prefix = "24"
            self.query_one("#subnet-ip", Input).value = subnet_ip
            self.query_one("#subnet-prefix", Input).value = prefix
            netmask = self._calculate_netmask_from_prefix(prefix)
            self.query_one("#subnet-netmask", Input).value = netmask

            self.query_one("#gateway", Input).value = settings.network.gateway
            self._last_gateway = settings.network.gateway  # Track for DNS auto-fill
            self.query_one("#dns-primary", Input).value = settings.network.dns_primary
            self.query_one("#dns-secondary", Input).value = settings.network.dns_secondary
            self.query_one("#domain-suffix", Input).value = settings.network.domain_suffix

            # SSL settings
            self.query_one("#domain", Input).value = settings.domain
            self.query_one("#email", Input).value = settings.email
            self.query_one("#ssl-provider", Input).value = settings.ssl.provider
            self.query_one("#ssl-staging", Checkbox).value = settings.ssl.staging
            self.query_one("#ssl-challenge", Select).value = settings.ssl.challenge_type
            self._update_dns_settings_visibility(settings.ssl.challenge_type)
            if settings.ssl.dns_provider:
                self.query_one("#dns-provider", Select).value = settings.ssl.dns_provider
            self.query_one("#dns-api-key", Input).value = settings.ssl.dns_api_key
            self.query_one("#dns-api-secret", Input).value = settings.ssl.dns_api_secret

            # Traefik settings
            self.query_one("#proxy-network", Input).value = settings.network.proxy_network
            self.query_one("#traefik-dashboard", Checkbox).value = settings.traefik.dashboard_enabled
            self.query_one("#traefik-access", Select).value = settings.traefik.dashboard_access
            self.query_one("#traefik-subdomain", Input).value = settings.traefik.dashboard_subdomain
            self.query_one("#traefik-username", Input).value = settings.traefik.dashboard_username
            self.query_one("#traefik-password", Input).value = settings.traefik.dashboard_password
            self._update_auth_fields_visibility(settings.traefik.dashboard_access)

            # Proxmox settings
            pve = settings.proxmox
            self.query_one("#pve-enabled", Checkbox).value = pve.enabled
            self.query_one("#pve-host", Input).value = pve.host
            self.query_one("#pve-port", Input).value = str(pve.port)
            self.query_one("#pve-user", Input).value = pve.user
            self.query_one("#pve-token-name", Input).value = pve.token_name
            self.query_one("#pve-token-value", Input).value = pve.token_value
            self.query_one("#pve-verify-ssl", Checkbox).value = pve.verify_ssl
            self.query_one("#pve-bridge", Input).value = pve.default_bridge

            # Store original select values (in case dropdowns don't get populated)
            self._original_pve_node = pve.default_node
            self._original_pve_storage = pve.default_storage
            self._original_pve_template_storage = pve.template_storage
            self._original_pve_template = pve.default_template

            # LXC defaults
            lxc = settings.lxc_defaults
            self.query_one("#lxc-memory", Input).value = str(lxc.memory)
            self.query_one("#lxc-swap", Input).value = str(lxc.swap)
            self.query_one("#lxc-cores", Input).value = str(lxc.cores)
            self.query_one("#lxc-disk", Input).value = str(lxc.rootfs_size)
            self.query_one("#lxc-unprivileged", Checkbox).value = lxc.unprivileged
            self.query_one("#lxc-onboot", Checkbox).value = lxc.start_on_boot
            self.query_one("#lxc-nesting", Checkbox).value = "nesting" in lxc.features

            # OPNsense settings
            opn = settings.opnsense
            self.query_one("#opnsense-enabled", Checkbox).value = opn.enabled
            self.query_one("#opnsense-host", Input).value = opn.host
            self.query_one("#opnsense-apikey", Input).value = opn.api_key
            self.query_one("#opnsense-apisecret", Input).value = opn.api_secret
            self.query_one("#opnsense-wan", Input).value = opn.wan_interface
            self.query_one("#opnsense-lan", Input).value = opn.lan_interface

            # Load Proxmox data if configured
            if pve.enabled and pve.host and pve.token_name and pve.token_value:
                self.load_proxmox_data()

        except Exception as e:
            self.show_status(f"Error loading settings: {e}", "error")

    def load_proxmox_data(self) -> None:
        """Load data from Proxmox API."""
        try:
            config_loader = get_config_loader()
            settings = config_loader.load_settings()
            pve = settings.proxmox

            api = ProxmoxAPI(
                host=pve.host,
                port=pve.port,
                user=pve.user,
                token_name=pve.token_name,
                token_value=pve.token_value,
                verify_ssl=pve.verify_ssl,
            )

            # Load nodes
            self.nodes = api.get_nodes()
            node_options = [(n["node"], n["node"]) for n in self.nodes]
            node_select = self.query_one("#pve-default-node", Select)
            node_select.set_options(node_options)
            if pve.default_node:
                node_select.value = pve.default_node
            elif self.nodes:
                node_select.value = self.nodes[0]["node"]

            # Load storage
            node = pve.default_node or (self.nodes[0]["node"] if self.nodes else None)
            if node:
                self.storages = api.get_storage_list(node)
                storage_options = [(s["storage"], s["storage"]) for s in self.storages]
                self.query_one("#pve-default-storage", Select).set_options(storage_options)
                self.query_one("#pve-template-storage", Select).set_options(storage_options)

                if pve.default_storage:
                    self.query_one("#pve-default-storage", Select).value = pve.default_storage
                if pve.template_storage:
                    self.query_one("#pve-template-storage", Select).value = pve.template_storage

                # Load templates
                self.load_templates(node, pve.template_storage or "local")

        except Exception as e:
            self.show_status(f"Error loading Proxmox data: {e}", "warning")

    def load_templates(self, node: str, storage: str) -> None:
        """Load templates for selected node and storage."""
        try:
            config_loader = get_config_loader()
            settings = config_loader.load_settings()
            pve = settings.proxmox

            api = ProxmoxAPI(
                host=pve.host,
                port=pve.port,
                user=pve.user,
                token_name=pve.token_name,
                token_value=pve.token_value,
                verify_ssl=pve.verify_ssl,
            )

            self.templates = api.get_lxc_templates(node, storage)
            template_options = []
            for t in self.templates:
                volid = t.get("volid", "")
                name = volid.split("/")[-1] if "/" in volid else volid
                template_options.append((name, volid))

            template_select = self.query_one("#pve-default-template", Select)
            template_select.set_options(template_options)

            if pve.default_template:
                for name, volid in template_options:
                    if pve.default_template in volid:
                        template_select.value = volid
                        break

        except Exception:
            pass

    def test_proxmox_connection(self) -> None:
        """Test Proxmox API connection."""
        result = self.query_one("#pve-connection-result", Static)
        result.update("[yellow]Testing...[/yellow]")

        try:
            host = self.query_one("#pve-host", Input).value.strip()
            port = int(self.query_one("#pve-port", Input).value or 8006)
            user = self.query_one("#pve-user", Input).value.strip()
            token_name = self.query_one("#pve-token-name", Input).value.strip()
            token_value = self.query_one("#pve-token-value", Input).value.strip()
            verify_ssl = self.query_one("#pve-verify-ssl", Checkbox).value

            if not all([host, token_name, token_value]):
                result.update("[red]Missing credentials[/red]")
                return

            api = ProxmoxAPI(
                host=host,
                port=port,
                user=user,
                token_name=token_name,
                token_value=token_value,
                verify_ssl=verify_ssl,
            )

            success, msg = api.test_connection()

            if success:
                result.update("[green]Connected![/green]")
                # Load data
                self.nodes = api.get_nodes()
                node_options = [(n["node"], n["node"]) for n in self.nodes]
                node_select = self.query_one("#pve-default-node", Select)
                node_select.set_options(node_options)
                if self.nodes:
                    node_select.value = self.nodes[0]["node"]

                # Load storage
                node = self.nodes[0]["node"] if self.nodes else None
                if node:
                    self.storages = api.get_storage_list(node)
                    if self.storages:
                        storage_options = [(s["storage"], s["storage"]) for s in self.storages]
                        self.query_one("#pve-default-storage", Select).set_options(storage_options)
                        self.query_one("#pve-template-storage", Select).set_options(storage_options)
                    else:
                        self.show_status("No storage found. Token may need Datastore.Audit permission.", "warning")

                self.show_status("Connected to Proxmox!", "success")
            else:
                result.update(f"[red]Failed: {msg}[/red]")

        except Exception as e:
            result.update(f"[red]Error: {e}[/red]")

    def save_settings(self) -> bool:
        """Save all settings."""
        try:
            config_loader = get_config_loader()

            # Build features string
            features = "nesting=1" if self.query_one("#lxc-nesting", Checkbox).value else ""

            # Build subnet from IP and prefix
            subnet_ip = self.query_one("#subnet-ip", Input).value.strip()
            subnet_prefix = self.query_one("#subnet-prefix", Input).value.strip() or "24"
            subnet = f"{subnet_ip}/{subnet_prefix}"

            # Build settings object
            settings = Settings(
                domain=self.query_one("#domain", Input).value.strip(),
                email=self.query_one("#email", Input).value.strip(),
                ssl=SSLConfig(
                    provider=self.query_one("#ssl-provider", Input).value.strip(),
                    staging=self.query_one("#ssl-staging", Checkbox).value,
                    challenge_type=self._get_select_value("#ssl-challenge") or "http",
                    dns_provider=self._get_select_value("#dns-provider"),
                    dns_api_key=self.query_one("#dns-api-key", Input).value.strip(),
                    dns_api_secret=self.query_one("#dns-api-secret", Input).value.strip(),
                ),
                network=InfraNetworkConfig(
                    subnet=subnet,
                    gateway=self.query_one("#gateway", Input).value.strip(),
                    dns_primary=self.query_one("#dns-primary", Input).value.strip(),
                    dns_secondary=self.query_one("#dns-secondary", Input).value.strip(),
                    domain_suffix=self.query_one("#domain-suffix", Input).value.strip(),
                    proxy_network=self.query_one("#proxy-network", Input).value.strip(),
                ),
                traefik=TraefikConfig(
                    dashboard_enabled=self.query_one("#traefik-dashboard", Checkbox).value,
                    dashboard_subdomain=self.query_one("#traefik-subdomain", Input).value.strip(),
                    dashboard_access=self._get_select_value("#traefik-access") or "local",
                    dashboard_username=self.query_one("#traefik-username", Input).value.strip(),
                    dashboard_password=self.query_one("#traefik-password", Input).value.strip(),
                ),
                proxmox=ProxmoxConfig(
                    enabled=self.query_one("#pve-enabled", Checkbox).value,
                    host=self.query_one("#pve-host", Input).value.strip(),
                    port=int(self.query_one("#pve-port", Input).value or 8006),
                    user=self.query_one("#pve-user", Input).value.strip(),
                    token_name=self.query_one("#pve-token-name", Input).value.strip(),
                    token_value=self.query_one("#pve-token-value", Input).value.strip(),
                    verify_ssl=self.query_one("#pve-verify-ssl", Checkbox).value,
                    default_node=self._get_pve_select_value("#pve-default-node", self._original_pve_node),
                    default_storage=self._get_pve_select_value("#pve-default-storage", self._original_pve_storage),
                    template_storage=self._get_pve_select_value("#pve-template-storage", self._original_pve_template_storage),
                    default_template=self._get_pve_select_value("#pve-default-template", self._original_pve_template),
                    default_bridge=self.query_one("#pve-bridge", Input).value.strip(),
                ),
                lxc_defaults=LXCDefaults(
                    memory=int(self.query_one("#lxc-memory", Input).value or 512),
                    swap=int(self.query_one("#lxc-swap", Input).value or 512),
                    cores=int(self.query_one("#lxc-cores", Input).value or 1),
                    rootfs_size=int(self.query_one("#lxc-disk", Input).value or 8),
                    unprivileged=self.query_one("#lxc-unprivileged", Checkbox).value,
                    start_on_boot=self.query_one("#lxc-onboot", Checkbox).value,
                    start_after_create=True,
                    features=features,
                ),
                opnsense=OPNsenseConfig(
                    enabled=self.query_one("#opnsense-enabled", Checkbox).value,
                    host=self.query_one("#opnsense-host", Input).value.strip(),
                    api_key=self.query_one("#opnsense-apikey", Input).value.strip(),
                    api_secret=self.query_one("#opnsense-apisecret", Input).value.strip(),
                    wan_interface=self.query_one("#opnsense-wan", Input).value.strip(),
                    lan_interface=self.query_one("#opnsense-lan", Input).value.strip(),
                ),
                first_run_complete=True,
            )

            config_loader.save_settings(settings)
            return True

        except Exception as e:
            self.show_status(f"Error saving settings: {e}", "error")
            return False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-ip":
            self.switch_section("ip")
        elif button_id == "btn-ssl":
            self.switch_section("ssl")
        elif button_id == "btn-traefik":
            self.switch_section("traefik")
        elif button_id == "btn-proxmox":
            self.switch_section("proxmox")
        elif button_id == "btn-opnsense":
            self.switch_section("opnsense")
        elif button_id == "btn-save":
            if self.save_settings():
                self.show_status("Settings saved successfully!", "success")
                self.notify("Settings saved")
        elif button_id == "btn-back":
            self.app.pop_screen()
        elif button_id == "btn-test-pve":
            self.test_proxmox_connection()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        input_id = event.input.id

        if input_id == "subnet-ip":
            # Auto-fill gateway and DNS when subnet IP changes
            prefix = self.query_one("#subnet-prefix", Input).value or "24"
            gateway = self._calculate_gateway_from_subnet(event.value, prefix)
            if gateway:
                gateway_input = self.query_one("#gateway", Input)
                dns_input = self.query_one("#dns-primary", Input)
                # Only auto-fill if empty or same as previous auto-fill
                if not gateway_input.value or gateway_input.value == self._last_gateway:
                    gateway_input.value = gateway
                if not dns_input.value or dns_input.value == self._last_gateway:
                    dns_input.value = gateway
                self._last_gateway = gateway

        elif input_id == "subnet-prefix":
            # Update netmask when prefix changes (avoid recursive loop)
            if not getattr(self, "_updating_subnet", False):
                self._updating_subnet = True
                netmask = self._calculate_netmask_from_prefix(event.value)
                self.query_one("#subnet-netmask", Input).value = netmask
                self._updating_subnet = False
            # Also update gateway if subnet IP is set
            subnet_ip = self.query_one("#subnet-ip", Input).value
            if subnet_ip:
                gateway = self._calculate_gateway_from_subnet(subnet_ip, event.value)
                if gateway:
                    gateway_input = self.query_one("#gateway", Input)
                    dns_input = self.query_one("#dns-primary", Input)
                    if not gateway_input.value or gateway_input.value == self._last_gateway:
                        gateway_input.value = gateway
                    if not dns_input.value or dns_input.value == self._last_gateway:
                        dns_input.value = gateway
                    self._last_gateway = gateway

        elif input_id == "subnet-netmask":
            # Update prefix when netmask changes (avoid recursive loop)
            if not getattr(self, "_updating_subnet", False):
                self._updating_subnet = True
                prefix = self._calculate_prefix_from_netmask(event.value)
                if prefix:
                    self.query_one("#subnet-prefix", Input).value = prefix
                else:
                    self.show_status("Invalid netmask format", "warning")
                self._updating_subnet = False

        elif input_id == "gateway":
            # Validate gateway is in subnet
            if event.value:
                self._validate_ip_in_subnet(event.value, "Gateway")
            # Auto-fill primary DNS from gateway
            dns_input = self.query_one("#dns-primary", Input)
            if not dns_input.value or dns_input.value == self._last_gateway:
                dns_input.value = event.value
            self._last_gateway = event.value

        elif input_id == "dns-primary":
            # Validate DNS is in subnet (optional - DNS can be external)
            if event.value:
                subnet_ip = self.query_one("#subnet-ip", Input).value.strip()
                prefix = self.query_one("#subnet-prefix", Input).value.strip() or "24"
                if subnet_ip and not self._is_ip_in_subnet(event.value, subnet_ip, prefix):
                    self.show_status(f"Note: Primary DNS ({event.value}) is outside subnet (external DNS)", "info")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes."""
        select_id = event.select.id

        if select_id == "ssl-challenge":
            # Show/hide DNS settings based on challenge type
            self._update_dns_settings_visibility(str(event.value) if event.value else "http")

        elif select_id == "traefik-access":
            # Show/hide auth fields based on access type
            self._update_auth_fields_visibility(str(event.value) if event.value else "local")

        elif select_id == "pve-template-storage":
            storage = event.value
            if storage and storage is not SELECT_BLANK:
                node = self._get_select_value("#pve-default-node")
                if node:
                    self.load_templates(node, str(storage))

        elif select_id == "pve-default-node":
            node = event.value
            if node and node is not SELECT_BLANK and self.nodes:
                # Reload storage for new node
                try:
                    config_loader = get_config_loader()
                    settings = config_loader.load_settings()
                    pve = settings.proxmox

                    api = ProxmoxAPI(
                        host=pve.host,
                        port=pve.port,
                        user=pve.user,
                        token_name=pve.token_name,
                        token_value=pve.token_value,
                        verify_ssl=pve.verify_ssl,
                    )

                    self.storages = api.get_storage_list(str(node))
                    if self.storages:
                        storage_options = [(s["storage"], s["storage"]) for s in self.storages]
                        self.query_one("#pve-default-storage", Select).set_options(storage_options)
                        self.query_one("#pve-template-storage", Select).set_options(storage_options)
                except Exception:
                    pass

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.app.pop_screen()
