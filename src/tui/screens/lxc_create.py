"""LXC Container creation screen."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Input,
    Label,
    ProgressBar,
    Rule,
    Select,
    Static,
)
from textual.worker import Worker, WorkerState

from ...core.config_loader import get_config_loader
from ...core.lxc_manager import LXCCreationConfig, get_lxc_manager
from ...core.proxmox_api import ProxmoxAPIError


class LXCCreateScreen(Screen):
    """Screen for creating new LXC containers via Proxmox."""

    CSS = """
    LXCCreateScreen {
        layout: vertical;
    }

    #create-container {
        height: 1fr;
        width: 100%;
    }

    #create-title {
        text-align: center;
        text-style: bold;
        padding: 1;
        height: auto;
    }

    #create-content {
        height: 1fr;
        min-height: 10;
        border: solid $primary;
        margin: 1 2;
        padding: 1;
        overflow-y: auto;
    }

    #create-content > Vertical {
        height: auto;
        width: 100%;
    }

    #create-buttons {
        height: auto;
        padding: 1;
        align: center middle;
    }

    #create-buttons Button {
        margin: 0 1;
    }

    #status-message {
        height: auto;
        text-align: center;
        padding: 1;
    }

    #progress-container {
        height: auto;
        margin: 1 2;
    }

    #log-output {
        height: auto;
        max-height: 10;
        border: solid $primary;
        margin: 1 2;
        padding: 1;
        background: $surface;
    }

    .resource-row {
        height: auto;
        width: 100%;
    }

    .resource-row > Vertical {
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
        self.creating = False
        self.log_messages = []

    def compose(self) -> ComposeResult:
        """Compose the LXC creation screen."""
        yield Vertical(
            Static("[bold]Create LXC Container[/bold]", id="create-title"),
            VerticalScroll(
                Vertical(
                    Static("[bold]Container Settings[/bold]"),
                    Rule(),
                    Label("Hostname:"),
                    Input(placeholder="e.g., worker-1", id="lxc-hostname"),
                    Label("Description:"),
                    Input(placeholder="Optional description", id="lxc-description"),
                    Label("Role:"),
                    Select(
                        [("Worker", "worker"), ("Traefik", "traefik"), ("Manager", "manager")],
                        id="lxc-role",
                        value="worker",
                    ),
                    Rule(),
                    Static("[bold]Network Configuration[/bold]"),
                    Label("IP Address:"),
                    Horizontal(
                        Input(placeholder="192.168.1.100", id="lxc-ip"),
                        Button("Pick Available", id="pick-ip", variant="default"),
                        classes="resource-row",
                    ),
                    Label("CIDR Prefix:"),
                    Input(placeholder="24", id="lxc-prefix", value="24"),
                    Rule(),
                    Static("[bold]Proxmox Settings[/bold]"),
                    Label("Node:"),
                    Select([], id="lxc-node", allow_blank=True),
                    Label("Template:"),
                    Select([], id="lxc-template", allow_blank=True),
                    Rule(),
                    Static("[bold]Resources[/bold]"),
                    Horizontal(
                        Vertical(
                            Label("Memory (MB):"),
                            Input(placeholder="512", id="lxc-memory", value="512"),
                        ),
                        Vertical(
                            Label("Swap (MB):"),
                            Input(placeholder="512", id="lxc-swap", value="512"),
                        ),
                        classes="resource-row",
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
                        classes="resource-row",
                    ),
                    Rule(),
                    Checkbox("Start container after creation", id="lxc-start", value=True),
                    Checkbox("Start on boot", id="lxc-onboot", value=True),
                    Checkbox("Enable nesting (for Docker)", id="lxc-nesting", value=True),
                ),
                id="create-content",
            ),
            Vertical(
                ProgressBar(total=100, id="create-progress"),
                id="progress-container",
            ),
            Static("", id="log-output"),
            Static("", id="status-message"),
            Horizontal(
                Button("Create Container", id="btn-create", variant="success"),
                Button("Cancel", id="btn-cancel", variant="default"),
                id="create-buttons",
            ),
            id="create-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen."""
        self.load_proxmox_data()

    def load_proxmox_data(self) -> None:
        """Load nodes and templates from Proxmox."""
        try:
            lxc_manager = get_lxc_manager()
            settings = get_config_loader().load_settings()

            if not settings.proxmox.enabled:
                self.show_status("Proxmox integration not enabled. Configure in Settings.", "error")
                return

            # Test connection
            success, msg = lxc_manager.test_connection()
            if not success:
                self.show_status(f"Proxmox connection failed: {msg}", "error")
                return

            # Load nodes
            self.nodes = lxc_manager.get_nodes()
            node_select = self.query_one("#lxc-node", Select)
            node_options = [(n["node"], n["node"]) for n in self.nodes]
            node_select.set_options(node_options)

            # Set default node
            if settings.proxmox.default_node:
                node_select.value = settings.proxmox.default_node
            elif self.nodes:
                node_select.value = self.nodes[0]["node"]

            # Load templates
            self.load_templates()

            self.show_status("Connected to Proxmox", "success")

        except ProxmoxAPIError as e:
            self.show_status(f"Proxmox error: {e}", "error")
        except Exception as e:
            self.show_status(f"Error: {e}", "error")

    def load_templates(self) -> None:
        """Load templates for selected node."""
        try:
            node_select = self.query_one("#lxc-node", Select)
            if not node_select.value:
                return

            lxc_manager = get_lxc_manager()
            self.templates = lxc_manager.get_templates(node_select.value)

            template_select = self.query_one("#lxc-template", Select)
            template_options = []

            for t in self.templates:
                volid = t.get("volid", "")
                # Extract template name from volid (e.g., "local:vztmpl/debian-12.tar.zst")
                name = volid.split("/")[-1] if "/" in volid else volid
                template_options.append((name, volid))

            template_select.set_options(template_options)

            # Set default
            settings = get_config_loader().load_settings()
            if settings.proxmox.default_template:
                for name, volid in template_options:
                    if settings.proxmox.default_template in volid:
                        template_select.value = volid
                        break
            elif template_options:
                # Prefer Debian
                for name, volid in template_options:
                    if "debian" in name.lower():
                        template_select.value = volid
                        break
                else:
                    template_select.value = template_options[0][1]

        except Exception as e:
            self.show_status(f"Error loading templates: {e}", "error")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes."""
        if event.select.id == "lxc-node":
            self.load_templates()

    def pick_available_ip(self) -> None:
        """Pick an available IP from the subnet."""
        config_loader = get_config_loader()
        available = config_loader.get_available_ips()

        if available:
            self.query_one("#lxc-ip", Input).value = available[0]
            self.show_status(f"Selected available IP: {available[0]}", "success")
        else:
            self.show_status("No available IPs in subnet", "error")

    def show_status(self, message: str, level: str = "info") -> None:
        """Show a status message."""
        status = self.query_one("#status-message", Static)
        if level == "error":
            status.update(f"[red]{message}[/red]")
        elif level == "success":
            status.update(f"[green]{message}[/green]")
        else:
            status.update(message)

    def add_log(self, message: str) -> None:
        """Add a log message."""
        self.log_messages.append(message)
        # Keep last 10 messages
        if len(self.log_messages) > 10:
            self.log_messages = self.log_messages[-10:]

        log_output = self.query_one("#log-output", Static)
        log_output.update("\n".join(self.log_messages))

    def validate_form(self) -> tuple[bool, str]:
        """Validate the form inputs."""
        hostname = self.query_one("#lxc-hostname", Input).value.strip()
        ip = self.query_one("#lxc-ip", Input).value.strip()
        node = self.query_one("#lxc-node", Select).value
        template = self.query_one("#lxc-template", Select).value

        if not hostname:
            return False, "Hostname is required"
        if not ip:
            return False, "IP address is required"
        if not node:
            return False, "Please select a Proxmox node"
        if not template:
            return False, "Please select a template"

        # Validate IP format
        try:
            parts = ip.split(".")
            if len(parts) != 4:
                raise ValueError()
            for p in parts:
                if not 0 <= int(p) <= 255:
                    raise ValueError()
        except (ValueError, AttributeError):
            return False, "Invalid IP address format"

        # Check if IP is already used
        config_loader = get_config_loader()
        vms = config_loader.load_vms()
        if vms.is_ip_used(ip):
            return False, f"IP address {ip} is already in use"

        return True, ""

    def create_container(self) -> None:
        """Start container creation in background."""
        valid, error = self.validate_form()
        if not valid:
            self.show_status(error, "error")
            return

        self.creating = True
        self.log_messages = []
        self.query_one("#btn-create", Button).disabled = True
        self.query_one("#create-progress", ProgressBar).update(progress=0)

        # Gather form data
        settings = get_config_loader().load_settings()
        config = LXCCreationConfig(
            hostname=self.query_one("#lxc-hostname", Input).value.strip(),
            ip_address=self.query_one("#lxc-ip", Input).value.strip(),
            netmask=self.query_one("#lxc-prefix", Input).value.strip(),
            gateway=settings.network.gateway,
            dns_primary=settings.network.dns_primary,
            dns_secondary=settings.network.dns_secondary,
            memory=int(self.query_one("#lxc-memory", Input).value or 512),
            swap=int(self.query_one("#lxc-swap", Input).value or 512),
            cores=int(self.query_one("#lxc-cores", Input).value or 1),
            rootfs_size=int(self.query_one("#lxc-disk", Input).value or 8),
            role=self.query_one("#lxc-role", Select).value,
            description=self.query_one("#lxc-description", Input).value.strip(),
            template=self.query_one("#lxc-template", Select).value,
            node=self.query_one("#lxc-node", Select).value,
        )

        # Run creation in worker thread
        self.run_worker(self._create_container_worker(config), name="create_lxc")

    async def _create_container_worker(self, config: LXCCreationConfig):
        """Worker to create container."""
        lxc_manager = get_lxc_manager()

        def progress_callback(msg: str):
            self.call_from_thread(self.add_log, msg)
            self.call_from_thread(self._update_progress)

        result = lxc_manager.create_container(config, progress_callback)
        return result

    def _update_progress(self) -> None:
        """Update progress bar."""
        progress = self.query_one("#create-progress", ProgressBar)
        current = progress.progress or 0
        if current < 90:
            progress.update(progress=current + 10)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.worker.name != "create_lxc":
            return

        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            self.creating = False
            self.query_one("#btn-create", Button).disabled = False
            self.query_one("#create-progress", ProgressBar).update(progress=100)

            if result.success:
                self.add_log(f"Container created: VMID {result.vmid}")
                self.add_log(f"SSH Key: {result.ssh_key_path}")
                self.show_status(result.message, "success")
                self.notify(f"Container {result.hostname} created!")
            else:
                self.show_status(result.error, "error")

        elif event.state == WorkerState.ERROR:
            self.creating = False
            self.query_one("#btn-create", Button).disabled = False
            self.show_status(f"Error: {event.worker.error}", "error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-create":
            self.create_container()

        elif button_id == "btn-cancel":
            self.app.pop_screen()

        elif button_id == "pick-ip":
            self.pick_available_ip()

    def action_cancel(self) -> None:
        """Cancel and go back."""
        if not self.creating:
            self.app.pop_screen()
