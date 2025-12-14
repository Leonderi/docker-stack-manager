"""Settings screen for global configuration."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Rule,
    Static,
)

from ...core.config_loader import (
    get_config_loader,
    InfraNetworkConfig,
    OPNsenseConfig,
    Settings,
    SSLConfig,
    TraefikConfig,
)


class SettingsScreen(Screen):
    """Screen for configuring global settings."""

    def compose(self) -> ComposeResult:
        """Compose the settings screen."""
        yield Container(
            Static("Settings", classes="title"),
            VerticalScroll(
                Static("[bold]Domain Configuration[/bold]"),
                Label("Domain Name:"),
                Input(placeholder="example.com", id="domain"),
                Label("Admin Email:"),
                Input(placeholder="admin@example.com", id="email"),
                Rule(),
                Static("[bold]SSL/TLS Configuration[/bold]"),
                Label("SSL Provider:"),
                Input(value="letsencrypt", id="ssl-provider"),
                Checkbox("Use Staging (for testing)", id="ssl-staging"),
                Rule(),
                Static("[bold]Infrastructure Network[/bold]"),
                Label("Subnet (CIDR):"),
                Input(placeholder="192.168.1.0/24", id="subnet"),
                Label("Gateway:"),
                Input(placeholder="192.168.1.1", id="gateway"),
                Rule(),
                Static("[bold]DNS Configuration[/bold]"),
                Label("Primary DNS:"),
                Input(placeholder="192.168.1.1", id="dns-primary"),
                Label("Secondary DNS:"),
                Input(placeholder="8.8.8.8", id="dns-secondary"),
                Label("Domain Suffix:"),
                Input(placeholder="local", id="domain-suffix"),
                Rule(),
                Static("[bold]Docker Network[/bold]"),
                Label("Proxy Network Name:"),
                Input(placeholder="traefik-public", id="proxy-network"),
                Rule(),
                Static("[bold]Traefik Dashboard[/bold]"),
                Checkbox("Enable Dashboard", id="traefik-dashboard"),
                Label("Dashboard Subdomain:"),
                Input(placeholder="traefik", id="traefik-subdomain"),
                Label("Dashboard Auth (htpasswd format):"),
                Input(placeholder="admin:$2y$05$...", id="traefik-auth", password=True),
                Static("[dim]Generate with: htpasswd -nB admin[/dim]"),
                Rule(),
                Static("[bold]OPNsense Firewall[/bold]"),
                Checkbox("Enable OPNsense Integration", id="opnsense-enabled"),
                Label("OPNsense Host:"),
                Input(placeholder="192.168.1.1", id="opnsense-host"),
                Label("API Key:"),
                Input(placeholder="API Key", id="opnsense-apikey"),
                Label("API Secret:"),
                Input(placeholder="API Secret", id="opnsense-apisecret", password=True),
                Label("WAN Interface:"),
                Input(placeholder="wan", id="opnsense-wan"),
                Label("LAN Interface:"),
                Input(placeholder="lan", id="opnsense-lan"),
                id="settings-scroll",
            ),
            Horizontal(
                Button("Save All", id="save-settings", variant="success"),
                Button("Reset", id="reset-settings", variant="warning"),
                Button("Proxmox Settings", id="proxmox-settings", variant="primary"),
                Button("Back", id="back", variant="default"),
                id="action-buttons",
            ),
            Static("", id="status-message"),
            id="main-content",
        )

    def on_mount(self) -> None:
        """Initialize the screen with current settings."""
        self.load_settings()

    def load_settings(self) -> None:
        """Load current settings into form."""
        try:
            config_loader = get_config_loader()
            settings = config_loader.load_settings(reload=True)

            # Domain & SSL
            self.query_one("#domain", Input).value = settings.domain
            self.query_one("#email", Input).value = settings.email
            self.query_one("#ssl-provider", Input).value = settings.ssl.provider
            self.query_one("#ssl-staging", Checkbox).value = settings.ssl.staging

            # Network
            self.query_one("#subnet", Input).value = settings.network.subnet
            self.query_one("#gateway", Input).value = settings.network.gateway
            self.query_one("#dns-primary", Input).value = settings.network.dns_primary
            self.query_one("#dns-secondary", Input).value = settings.network.dns_secondary
            self.query_one("#domain-suffix", Input).value = settings.network.domain_suffix
            self.query_one("#proxy-network", Input).value = settings.network.proxy_network

            # Traefik
            self.query_one("#traefik-dashboard", Checkbox).value = settings.traefik.dashboard_enabled
            self.query_one("#traefik-subdomain", Input).value = settings.traefik.dashboard_subdomain
            self.query_one("#traefik-auth", Input).value = settings.traefik.dashboard_auth

            # OPNsense
            self.query_one("#opnsense-enabled", Checkbox).value = settings.opnsense.enabled
            self.query_one("#opnsense-host", Input).value = settings.opnsense.host
            self.query_one("#opnsense-apikey", Input).value = settings.opnsense.api_key
            self.query_one("#opnsense-apisecret", Input).value = settings.opnsense.api_secret
            self.query_one("#opnsense-wan", Input).value = settings.opnsense.wan_interface
            self.query_one("#opnsense-lan", Input).value = settings.opnsense.lan_interface

        except Exception as e:
            self.show_status(f"Error loading settings: {e}", "error")

    def save_settings(self) -> bool:
        """Save settings from form."""
        try:
            config_loader = get_config_loader()

            # Build settings object
            settings = Settings(
                domain=self.query_one("#domain", Input).value.strip(),
                email=self.query_one("#email", Input).value.strip(),
                ssl=SSLConfig(
                    provider=self.query_one("#ssl-provider", Input).value.strip(),
                    staging=self.query_one("#ssl-staging", Checkbox).value,
                ),
                network=InfraNetworkConfig(
                    subnet=self.query_one("#subnet", Input).value.strip(),
                    gateway=self.query_one("#gateway", Input).value.strip(),
                    dns_primary=self.query_one("#dns-primary", Input).value.strip(),
                    dns_secondary=self.query_one("#dns-secondary", Input).value.strip(),
                    domain_suffix=self.query_one("#domain-suffix", Input).value.strip(),
                    proxy_network=self.query_one("#proxy-network", Input).value.strip(),
                ),
                traefik=TraefikConfig(
                    dashboard_enabled=self.query_one("#traefik-dashboard", Checkbox).value,
                    dashboard_subdomain=self.query_one("#traefik-subdomain", Input).value.strip(),
                    dashboard_auth=self.query_one("#traefik-auth", Input).value.strip(),
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

    def show_status(self, message: str, level: str = "info") -> None:
        """Show a status message."""
        status = self.query_one("#status-message", Static)
        if level == "error":
            status.update(f"[red]{message}[/red]")
        elif level == "success":
            status.update(f"[green]{message}[/green]")
        else:
            status.update(message)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "save-settings":
            if self.save_settings():
                self.show_status("Settings saved successfully!", "success")
                self.notify("Settings saved")

        elif button_id == "reset-settings":
            self.load_settings()
            self.show_status("Settings reset to last saved values", "info")

        elif button_id == "proxmox-settings":
            self.app.push_screen("proxmox_settings")

        elif button_id == "back":
            self.app.pop_screen()
