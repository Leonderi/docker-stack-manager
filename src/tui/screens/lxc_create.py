"""LXC Container creation screen."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
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

from ..base_screen import BaseScreen
from ...core.config_loader import get_config_loader
from ...core.lxc_manager import LXCCreationConfig, LXCCreationResult, get_lxc_manager
from ...core.proxmox_api import ProxmoxAPIError
from ...core.ssh_manager import get_vm_initializer


class LXCCreateScreen(BaseScreen):
    """Screen for creating new LXC containers via Proxmox."""

    CSS = """
    LXCCreateScreen {
        layout: vertical;
        height: 100%;
    }

    LXCCreateScreen VerticalScroll {
        height: 1fr;
        max-height: 100%;
    }

    #create-container {
        height: 1fr;
    }

    #create-title {
        text-align: center;
        text-style: bold;
        padding: 1;
        height: auto;
    }

    #create-content {
        height: 1fr;
        max-height: 100%;
        border: solid $primary;
        margin: 0 1;
        padding: 1;
    }

    #create-content > Vertical {
        height: auto;
    }

    #create-buttons {
        height: auto;
        padding: 1;
        align: center middle;
    }

    #status-message {
        height: auto;
        text-align: center;
    }

    #progress-container {
        height: auto;
        margin: 0 1;
        align: left middle;
    }

    #progress-container ProgressBar {
        width: 1fr;
    }

    #progress-container Checkbox {
        width: auto;
        margin-left: 2;
    }

    #log-output {
        height: auto;
        max-height: 15;
        border: solid $primary;
        margin: 0 1;
        padding: 1;
        background: $surface;
        overflow-y: auto;
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

    .resource-row > Input {
        width: 1fr;
    }

    .resource-row > Button {
        width: auto;
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
        self._created_hostname = None
        self._initializing = False

    def compose(self) -> ComposeResult:
        """Compose the LXC creation screen."""
        yield Vertical(
            Static("[bold]Create LXC Container[/bold]", id="create-title"),
            VerticalScroll(
                Vertical(
                    # Role first - determines hostname
                    Static("[bold]Role & Identity[/bold]"),
                    Rule(),
                    Label("Role:"),
                    Select(
                        [("Worker", "worker"), ("Traefik (Reverse Proxy)", "traefik")],
                        id="lxc-role",
                        value="worker",
                    ),
                    Static("", id="role-info"),
                    Label("Hostname:"),
                    Input(placeholder="auto-generated", id="lxc-hostname"),
                    Label("Description:"),
                    Input(placeholder="Optional description", id="lxc-description"),
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
                    Label("Container ID (VMID):"),
                    Horizontal(
                        Input(placeholder="Auto (leave empty)", id="lxc-vmid"),
                        Button("Check", id="check-vmid", variant="default"),
                        Button("Next Free", id="next-vmid", variant="default"),
                        classes="resource-row",
                    ),
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
            Horizontal(
                ProgressBar(total=100, id="create-progress"),
                Checkbox("Show Details", id="show-details"),
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
        self._check_traefik_exists()
        self._generate_hostname()

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
        elif event.select.id == "lxc-role":
            self._generate_hostname()
            self._update_role_info()

    def _check_traefik_exists(self) -> None:
        """Check if a Traefik container already exists and update UI."""
        config_loader = get_config_loader()
        vms = config_loader.load_vms()
        traefik_vm = vms.get_traefik_vm()

        role_select = self.query_one("#lxc-role", Select)
        role_info = self.query_one("#role-info", Static)

        if traefik_vm:
            # Traefik exists - remove from options or show warning
            role_select.set_options([("Worker", "worker")])
            role_select.value = "worker"
            role_info.update(f"[yellow]Traefik already exists: {traefik_vm.name}[/yellow]")
        else:
            role_select.set_options([
                ("Worker", "worker"),
                ("Traefik (Reverse Proxy)", "traefik")
            ])
            role_info.update("")

    def _update_role_info(self) -> None:
        """Update role info text based on selection."""
        role = self.query_one("#lxc-role", Select).value
        role_info = self.query_one("#role-info", Static)

        if role == "traefik":
            role_info.update("[cyan]Traefik handles SSL and routing for all services[/cyan]")
        else:
            role_info.update("")

    def _generate_hostname(self) -> None:
        """Auto-generate hostname based on role."""
        role = self.query_one("#lxc-role", Select).value
        hostname_input = self.query_one("#lxc-hostname", Input)

        config_loader = get_config_loader()
        vms = config_loader.load_vms()

        if role == "traefik":
            hostname_input.value = "traefik"
        else:
            # Find next available worker number
            existing_workers = [v.name for v in vms.vms if v.name.startswith("worker-")]
            worker_num = 1
            while f"worker-{worker_num}" in existing_workers:
                worker_num += 1
            hostname_input.value = f"worker-{worker_num}"

    def pick_available_ip(self) -> None:
        """Pick an available IP from the subnet."""
        config_loader = get_config_loader()
        available = config_loader.get_available_ips()

        if available:
            self.query_one("#lxc-ip", Input).value = available[0]
            self.show_status(f"Selected available IP: {available[0]}", "success")
        else:
            self.show_status("No available IPs in subnet", "error")

    def check_vmid_availability(self) -> None:
        """Check if the entered VMID is available."""
        vmid_input = self.query_one("#lxc-vmid", Input).value.strip()
        if not vmid_input:
            self.show_status("Enter a VMID to check", "info")
            return

        try:
            vmid = int(vmid_input)
            if vmid < 100:
                self.show_status("VMID must be >= 100", "error")
                return

            lxc_manager = get_lxc_manager()
            if lxc_manager.is_vmid_available(vmid):
                self.show_status(f"VMID {vmid} is available", "success")
            else:
                self.show_status(f"VMID {vmid} is already in use", "error")
        except ValueError:
            self.show_status("VMID must be a number", "error")
        except Exception as e:
            self.show_status(f"Error checking VMID: {e}", "error")

    def get_next_free_vmid(self) -> None:
        """Get and fill in the next free VMID."""
        try:
            lxc_manager = get_lxc_manager()
            vmid = lxc_manager.get_next_vmid()
            self.query_one("#lxc-vmid", Input).value = str(vmid)
            self.show_status(f"Next available VMID: {vmid}", "success")
        except Exception as e:
            self.show_status(f"Error getting next VMID: {e}", "error")

    def add_log(self, message: str) -> None:
        """Add a log message."""
        self.log_messages.append(message)
        # Keep last 30 messages (more for details mode)
        max_messages = 30
        if len(self.log_messages) > max_messages:
            self.log_messages = self.log_messages[-max_messages:]

        log_output = self.query_one("#log-output", Static)
        log_output.update("\n".join(self.log_messages))

    def add_detail_log(self, message: str) -> None:
        """Add a detail log message (only if Show Details is enabled)."""
        try:
            show_details = self.query_one("#show-details", Checkbox).value
            if show_details:
                self.add_log(f"[dim]{message}[/dim]")
        except Exception:
            pass

    def validate_form(self) -> tuple[bool, str]:
        """Validate the form inputs."""
        hostname = self.query_one("#lxc-hostname", Input).value.strip()
        ip = self.query_one("#lxc-ip", Input).value.strip()
        node = self.query_one("#lxc-node", Select).value
        template = self.query_one("#lxc-template", Select).value
        vmid_str = self.query_one("#lxc-vmid", Input).value.strip()

        if not hostname:
            return False, "Hostname is required"
        if not ip:
            return False, "IP address is required"
        if not node:
            return False, "Please select a Proxmox node"
        if not template:
            return False, "Please select a template"

        # Validate VMID if provided
        if vmid_str:
            try:
                vmid = int(vmid_str)
                if vmid < 100:
                    return False, "VMID must be >= 100"
            except ValueError:
                return False, "VMID must be a number"

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
        vmid_str = self.query_one("#lxc-vmid", Input).value.strip()
        vmid = int(vmid_str) if vmid_str else 0

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
            vmid=vmid,
        )

        # Run creation in worker thread
        self._current_config = config
        self.run_worker(
            self._create_container_worker,
            name="create_lxc",
            thread=True,
        )

    def _create_container_worker(self) -> LXCCreationResult:
        """Worker to create container (runs in thread)."""
        lxc_manager = get_lxc_manager()
        config = self._current_config

        def progress_callback(msg: str):
            self.app.call_from_thread(self.add_log, msg)
            self.app.call_from_thread(self._update_progress)

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
        if event.worker.name == "initialize_vm":
            self._handle_init_worker_state(event)
            return

        if event.worker.name != "create_lxc":
            return

        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            self.creating = False
            self.query_one("#create-progress", ProgressBar).update(progress=100)

            if result.success:
                self.add_log(f"Container created: VMID {result.vmid}")
                self.add_log(f"SSH Key (root): {result.ssh_key_path}")
                self.add_log("Click 'Initialize Now' to set up manager user")
                self.show_status(f"{result.message}", "success")
                self.notify(f"Container {result.hostname} created!")

                # Store created container name for initialization
                self._created_hostname = result.hostname

                # Change buttons after successful creation
                btn_create = self.query_one("#btn-create", Button)
                btn_cancel = self.query_one("#btn-cancel", Button)
                btn_create.label = "Initialize Now"
                btn_create.variant = "warning"
                btn_create.disabled = False
                btn_cancel.label = "Back"
                btn_cancel.variant = "default"
            else:
                self.query_one("#btn-create", Button).disabled = False
                self.show_status(result.error, "error")

        elif event.state == WorkerState.ERROR:
            self.creating = False
            self.query_one("#btn-create", Button).disabled = False
            self.show_status(f"Error: {event.worker.error}", "error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-create":
            btn_create = self.query_one("#btn-create", Button)
            btn_cancel = self.query_one("#btn-cancel", Button)
            label = str(btn_create.label)

            if label == "Initialize Now" or label == "Retry Initialize":
                # Start initialization for the created container
                self.start_initialization()
            elif label == "Create Another":
                # Reset form for new container
                self._reset_form()
            else:
                self.create_container()

        elif button_id == "btn-cancel":
            self.app.pop_screen()

        elif button_id == "pick-ip":
            self.pick_available_ip()

        elif button_id == "check-vmid":
            self.check_vmid_availability()

        elif button_id == "next-vmid":
            self.get_next_free_vmid()

    def action_cancel(self) -> None:
        """Cancel and go back."""
        if not self.creating and not self._initializing:
            self.app.pop_screen()

    def _reset_form(self) -> None:
        """Reset form for creating another container."""
        self._created_hostname = None
        self._init_vm = None
        self.log_messages = []

        # Reset form fields
        self.query_one("#lxc-description", Input).value = ""
        self.query_one("#lxc-ip", Input).value = ""
        self.query_one("#lxc-vmid", Input).value = ""

        # Reset progress and log
        self.query_one("#create-progress", ProgressBar).update(progress=0)
        self.query_one("#log-output", Static).update("")

        # Reset buttons
        btn_create = self.query_one("#btn-create", Button)
        btn_cancel = self.query_one("#btn-cancel", Button)
        btn_create.label = "Create Container"
        btn_create.variant = "success"
        btn_cancel.label = "Cancel"
        btn_cancel.variant = "default"

        # Check traefik and regenerate hostname
        self._check_traefik_exists()
        self._generate_hostname()

        self.show_status("Ready to create a new container")

    def start_initialization(self) -> None:
        """Start initialization for the created container."""
        if not self._created_hostname:
            self.show_status("No container to initialize", "error")
            return

        config_loader = get_config_loader()
        vms = config_loader.load_vms()
        vm = vms.get_vm_by_name(self._created_hostname)

        if not vm:
            self.show_status(f"Container {self._created_hostname} not found", "error")
            return

        if vm.initialized:
            self.show_status(f"{vm.name} is already initialized", "warning")
            return

        if not vm.ssh_key:
            self.show_status("Container has no SSH key configured", "error")
            return

        self._initializing = True
        self._init_vm = vm
        self.log_messages = []
        self.query_one("#btn-create", Button).disabled = True
        self.query_one("#create-progress", ProgressBar).update(progress=0)
        self.add_log(f"Starting initialization of {vm.name}...")
        self.show_status(f"Initializing {vm.name}... This may take several minutes.")

        # Run initialization in worker thread
        self.run_worker(
            self._initialize_worker,
            name="initialize_vm",
            thread=True,
        )

    def _initialize_worker(self) -> tuple[bool, str, str]:
        """Worker to initialize container (runs in thread)."""
        from pathlib import Path

        vm = self._init_vm
        initializer = get_vm_initializer()

        def progress_callback(msg: str):
            self.app.call_from_thread(self.add_log, msg)
            self.app.call_from_thread(self._update_progress)

        def detail_callback(msg: str):
            self.app.call_from_thread(self.add_detail_log, msg)

        success, manager_key_path, message = initializer.initialize_vm(
            host=vm.host,
            root_key_path=Path(vm.ssh_key),
            vm_name=vm.name,
            callback=progress_callback,
            detail_callback=detail_callback,
            port=vm.ssh_port,
        )

        return success, str(manager_key_path), message

    def _handle_init_worker_state(self, event: Worker.StateChanged) -> None:
        """Handle initialization worker state changes."""
        if event.state == WorkerState.SUCCESS:
            success, manager_key_path, message = event.worker.result
            self._initializing = False
            self.query_one("#create-progress", ProgressBar).update(progress=100)

            if success:
                # Update VM config with new manager key
                config_loader = get_config_loader()
                vm = self._init_vm
                vm.user = "manager"
                vm.ssh_key = manager_key_path
                vm.initialized = True
                config_loader.update_vm(vm.name, vm)

                self.add_log("")
                self.add_log("[bold green]========================================[/bold green]")
                self.add_log("[bold green]   INITIALIZATION COMPLETE![/bold green]")
                self.add_log("[bold green]========================================[/bold green]")
                self.add_log("")
                self.add_log(f"VM: {vm.name}")
                self.add_log(f"User: manager")
                self.add_log(f"SSH Key: {manager_key_path}")
                self.add_log("")
                self.show_status(f"{vm.name} initialized successfully!", "success")
                self.notify(f"{vm.name} is ready to use!", title="Initialization Complete")

                # Update buttons
                btn_create = self.query_one("#btn-create", Button)
                btn_cancel = self.query_one("#btn-cancel", Button)
                btn_create.label = "Create Another"
                btn_create.variant = "success"
                btn_create.disabled = False
                btn_cancel.label = "Done"
                btn_cancel.variant = "primary"
            else:
                self.add_log("")
                self.add_log("[bold red]========================================[/bold red]")
                self.add_log("[bold red]   INITIALIZATION FAILED![/bold red]")
                self.add_log("[bold red]========================================[/bold red]")
                self.add_log(f"Error: {message}")
                self.show_status(f"Initialization failed: {message}", "error")
                btn_create = self.query_one("#btn-create", Button)
                btn_create.label = "Retry Initialize"
                btn_create.disabled = False

        elif event.state == WorkerState.ERROR:
            self._initializing = False
            self.query_one("#btn-create", Button).disabled = False
            self.add_log(f"Error: {event.worker.error}")
            self.show_status(f"Error: {event.worker.error}", "error")
