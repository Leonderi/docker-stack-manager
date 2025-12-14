"""Proxmox configuration screen."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
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

from ...core.config_loader import ProxmoxConfig, LXCDefaults, get_config_loader
from ...core.proxmox_api import ProxmoxAPI, ProxmoxAPIError


class ProxmoxSettingsScreen(Screen):
    """Screen for configuring Proxmox integration."""

    CSS = """
    ProxmoxSettingsScreen {
        layout: vertical;
    }

    #settings-container {
        height: 1fr;
        width: 100%;
    }

    #settings-title {
        text-align: center;
        text-style: bold;
        padding: 1;
        height: auto;
    }

    #settings-content {
        height: 1fr;
        min-height: 10;
        border: solid $primary;
        margin: 1 2;
        padding: 1;
        overflow-y: auto;
    }

    #settings-content > Vertical {
        height: auto;
        width: 100%;
    }

    #settings-buttons {
        height: auto;
        padding: 1;
        align: center middle;
    }

    #settings-buttons Button {
        margin: 0 1;
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
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self):
        super().__init__()
        self.nodes = []
        self.templates = []
        self.storages = []

    def compose(self) -> ComposeResult:
        """Compose the settings screen."""
        yield Vertical(
            Static("[bold]Proxmox VE Configuration[/bold]", id="settings-title"),
            VerticalScroll(
                Vertical(
                    Checkbox("Enable Proxmox Integration", id="pve-enabled"),
                    Rule(),
                    Static("[bold]Connection Settings[/bold]"),
                    Label("Proxmox Host:"),
                    Input(placeholder="192.168.1.10 or proxmox.local", id="pve-host"),
                    Horizontal(
                        Vertical(
                            Label("Port:"),
                            Input(placeholder="8006", id="pve-port", value="8006"),
                        ),
                        Vertical(
                            Label("User:"),
                            Input(placeholder="root@pam", id="pve-user", value="root@pam"),
                        ),
                        classes="row",
                    ),
                    Rule(),
                    Static("[bold]API Token[/bold]"),
                    Static("[dim]Create a token in Proxmox: Datacenter > Permissions > API Tokens[/dim]"),
                    Label("Token Name:"),
                    Input(placeholder="docker-manager", id="pve-token-name"),
                    Label("Token Value (UUID):"),
                    Input(placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", id="pve-token-value", password=True),
                    Checkbox("Verify SSL Certificate", id="pve-verify-ssl"),
                    Horizontal(
                        Button("Test Connection", id="btn-test", variant="primary"),
                        Static("", id="test-result"),
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
                    Checkbox("Unprivileged containers", id="lxc-unprivileged", value=True),
                    Checkbox("Start on boot", id="lxc-onboot", value=True),
                    Checkbox("Enable nesting (for Docker)", id="lxc-nesting", value=True),
                ),
                id="settings-content",
            ),
            Static("", id="status-message"),
            Horizontal(
                Button("Save", id="btn-save", variant="success"),
                Button("Cancel", id="btn-cancel", variant="default"),
                id="settings-buttons",
            ),
            id="settings-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Load current settings."""
        self.load_settings()

    def load_settings(self) -> None:
        """Load settings from config."""
        try:
            config_loader = get_config_loader()
            settings = config_loader.load_settings()
            pve = settings.proxmox
            lxc = settings.lxc_defaults

            # Connection settings
            self.query_one("#pve-enabled", Checkbox).value = pve.enabled
            self.query_one("#pve-host", Input).value = pve.host
            self.query_one("#pve-port", Input).value = str(pve.port)
            self.query_one("#pve-user", Input).value = pve.user
            self.query_one("#pve-token-name", Input).value = pve.token_name
            self.query_one("#pve-token-value", Input).value = pve.token_value
            self.query_one("#pve-verify-ssl", Checkbox).value = pve.verify_ssl
            self.query_one("#pve-bridge", Input).value = pve.default_bridge

            # LXC defaults
            self.query_one("#lxc-memory", Input).value = str(lxc.memory)
            self.query_one("#lxc-swap", Input).value = str(lxc.swap)
            self.query_one("#lxc-cores", Input).value = str(lxc.cores)
            self.query_one("#lxc-disk", Input).value = str(lxc.rootfs_size)
            self.query_one("#lxc-unprivileged", Checkbox).value = lxc.unprivileged
            self.query_one("#lxc-onboot", Checkbox).value = lxc.start_on_boot
            self.query_one("#lxc-nesting", Checkbox).value = "nesting=1" in lxc.features

            # If connected, load dynamic data
            if pve.enabled and pve.host and pve.token_name and pve.token_value:
                self.load_proxmox_data()

        except Exception as e:
            self.show_status(f"Error loading settings: {e}", "error")

    def load_proxmox_data(self) -> None:
        """Load nodes, storage, and templates from Proxmox."""
        try:
            settings = get_config_loader().load_settings()
            pve = settings.proxmox

            api = ProxmoxAPI(
                host=pve.host,
                user=pve.user,
                token_name=pve.token_name,
                token_value=pve.token_value,
                port=pve.port,
                verify_ssl=pve.verify_ssl,
            )

            # Load nodes
            self.nodes = api.get_nodes()
            node_select = self.query_one("#pve-default-node", Select)
            node_options = [(n["node"], n["node"]) for n in self.nodes]
            node_select.set_options(node_options)
            if pve.default_node and pve.default_node in [n["node"] for n in self.nodes]:
                node_select.value = pve.default_node
            elif self.nodes:
                node_select.value = self.nodes[0]["node"]

            # Load storage
            if self.nodes:
                node = pve.default_node or self.nodes[0]["node"]
                self.storages = api.get_storage_list(node)
                storage_options = [(s["storage"], s["storage"]) for s in self.storages]

                storage_select = self.query_one("#pve-default-storage", Select)
                storage_select.set_options(storage_options)
                if pve.default_storage:
                    storage_select.value = pve.default_storage

                template_storage_select = self.query_one("#pve-template-storage", Select)
                template_storage_select.set_options(storage_options)
                if pve.template_storage:
                    template_storage_select.value = pve.template_storage

                # Load templates
                self.load_templates(node, pve.template_storage or "local")

        except ProxmoxAPIError as e:
            self.show_status(f"Could not load Proxmox data: {e}", "error")
        except Exception as e:
            self.show_status(f"Error: {e}", "error")

    def load_templates(self, node: str, storage: str) -> None:
        """Load templates from Proxmox."""
        try:
            settings = get_config_loader().load_settings()
            pve = settings.proxmox

            api = ProxmoxAPI(
                host=pve.host,
                user=pve.user,
                token_name=pve.token_name,
                token_value=pve.token_value,
                port=pve.port,
                verify_ssl=pve.verify_ssl,
            )

            self.templates = api.get_lxc_templates(node, storage)
            template_select = self.query_one("#pve-default-template", Select)

            template_options = []
            for t in self.templates:
                volid = t.get("volid", "")
                name = volid.split("/")[-1] if "/" in volid else volid
                template_options.append((name, volid))

            template_select.set_options(template_options)
            if pve.default_template:
                for name, volid in template_options:
                    if pve.default_template in volid:
                        template_select.value = volid
                        break

        except Exception:
            pass

    def test_connection(self) -> None:
        """Test the Proxmox connection."""
        try:
            host = self.query_one("#pve-host", Input).value.strip()
            port = int(self.query_one("#pve-port", Input).value or 8006)
            user = self.query_one("#pve-user", Input).value.strip()
            token_name = self.query_one("#pve-token-name", Input).value.strip()
            token_value = self.query_one("#pve-token-value", Input).value.strip()
            verify_ssl = self.query_one("#pve-verify-ssl", Checkbox).value

            if not all([host, user, token_name, token_value]):
                self.show_status("Please fill in all connection fields", "error")
                return

            api = ProxmoxAPI(
                host=host,
                user=user,
                token_name=token_name,
                token_value=token_value,
                port=port,
                verify_ssl=verify_ssl,
            )

            success, msg = api.test_connection()
            result = self.query_one("#test-result", Static)

            if success:
                result.update(f"[green]{msg}[/green]")
                self.show_status("Connection successful!", "success")

                # Load dynamic data
                self.nodes = api.get_nodes()
                node_select = self.query_one("#pve-default-node", Select)
                node_options = [(n["node"], n["node"]) for n in self.nodes]
                node_select.set_options(node_options)
                if self.nodes:
                    node_select.value = self.nodes[0]["node"]

                    # Load storage
                    self.storages = api.get_storage_list(self.nodes[0]["node"])
                    storage_options = [(s["storage"], s["storage"]) for s in self.storages]
                    self.query_one("#pve-default-storage", Select).set_options(storage_options)
                    self.query_one("#pve-template-storage", Select).set_options(storage_options)

            else:
                result.update(f"[red]Failed: {msg}[/red]")
                self.show_status(f"Connection failed: {msg}", "error")

        except Exception as e:
            self.show_status(f"Error: {e}", "error")

    def save_settings(self) -> None:
        """Save settings to config."""
        try:
            config_loader = get_config_loader()
            settings = config_loader.load_settings()

            # Build Proxmox config
            features = "nesting=1" if self.query_one("#lxc-nesting", Checkbox).value else ""

            settings.proxmox = ProxmoxConfig(
                enabled=self.query_one("#pve-enabled", Checkbox).value,
                host=self.query_one("#pve-host", Input).value.strip(),
                port=int(self.query_one("#pve-port", Input).value or 8006),
                user=self.query_one("#pve-user", Input).value.strip(),
                token_name=self.query_one("#pve-token-name", Input).value.strip(),
                token_value=self.query_one("#pve-token-value", Input).value.strip(),
                verify_ssl=self.query_one("#pve-verify-ssl", Checkbox).value,
                default_node=self.query_one("#pve-default-node", Select).value or "",
                default_storage=self.query_one("#pve-default-storage", Select).value or "",
                template_storage=self.query_one("#pve-template-storage", Select).value or "",
                default_template=self.query_one("#pve-default-template", Select).value or "",
                default_bridge=self.query_one("#pve-bridge", Input).value.strip(),
            )

            settings.lxc_defaults = LXCDefaults(
                memory=int(self.query_one("#lxc-memory", Input).value or 512),
                swap=int(self.query_one("#lxc-swap", Input).value or 512),
                cores=int(self.query_one("#lxc-cores", Input).value or 1),
                rootfs_size=int(self.query_one("#lxc-disk", Input).value or 8),
                unprivileged=self.query_one("#lxc-unprivileged", Checkbox).value,
                start_on_boot=self.query_one("#lxc-onboot", Checkbox).value,
                start_after_create=True,
                features=features,
            )

            config_loader.save_settings(settings)
            self.show_status("Settings saved!", "success")
            self.notify("Proxmox settings saved")

        except Exception as e:
            self.show_status(f"Error saving: {e}", "error")

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

        if button_id == "btn-test":
            self.test_connection()

        elif button_id == "btn-save":
            self.save_settings()

        elif button_id == "btn-cancel":
            self.app.pop_screen()

    def action_cancel(self) -> None:
        """Cancel and go back."""
        self.app.pop_screen()
