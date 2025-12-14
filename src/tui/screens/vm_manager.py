"""VM Manager screen for managing VMs and LXC containers."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
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
from ...core.config_loader import VMConfig, VMNetworkConfig, get_config_loader
from ...core.ssh_manager import get_ssh_manager, get_vm_initializer


class VMManagerScreen(BaseScreen):
    """Screen for managing VMs and LXC containers."""

    CSS = """
    VMManagerScreen {
        layout: vertical;
    }

    #vm-manager-title {
        width: 100%;
        height: auto;
        content-align: center middle;
        text-style: bold;
        color: $primary;
        padding: 1;
    }

    #main-content {
        height: 1fr;
    }

    #vm-list-section {
        width: 2fr;
        height: 100%;
        border: solid $primary;
        margin: 0 1 1 1;
        padding: 1;
    }

    #vm-form-section {
        width: 1fr;
        height: 100%;
        border: solid $primary;
        margin: 0 1 1 0;
        padding: 1;
    }

    #vm-table {
        height: 1fr;
        margin-bottom: 1;
    }

    #list-buttons {
        height: auto;
        margin-top: 1;
    }

    #list-buttons Button {
        margin-right: 1;
    }

    #action-buttons {
        height: auto;
        margin-top: 1;
        padding-top: 1;
        border-top: solid $primary;
    }

    #action-buttons Button {
        margin-right: 1;
    }

    #vm-form-scroll {
        height: 1fr;
    }

    #form-buttons {
        height: auto;
        margin-top: 1;
    }

    #form-buttons Button {
        margin-right: 1;
    }

    #status-message {
        height: auto;
        padding: 1;
        text-align: center;
    }

    #selected-info {
        height: auto;
        padding: 1;
        background: $surface;
    }

    .success {
        color: $success;
    }

    .error {
        color: $error;
    }

    .warning {
        color: $warning;
    }

    #init-log-container {
        height: auto;
        margin: 0 1;
        display: none;
    }

    #init-log-container.visible {
        display: block;
    }

    #init-progress {
        margin-bottom: 1;
    }

    #init-log-output {
        height: auto;
        max-height: 10;
        border: solid $primary;
        padding: 1;
        background: $surface;
    }
    """

    def __init__(self):
        super().__init__()
        self.editing_vm = None
        self._init_vm = None
        self._delete_vm = None
        self.log_messages = []

    def compose(self) -> ComposeResult:
        """Compose the VM manager screen."""
        yield Static("[bold]VM & Container Management[/bold]", id="vm-manager-title")
        yield Container(
            Horizontal(
                # Left: VM List
                Vertical(
                    DataTable(id="vm-table"),
                    # Top buttons: Create/Add
                    Horizontal(
                        Button("Create LXC", id="create-lxc", variant="success"),
                        Button("Add Existing", id="add-existing", variant="primary"),
                        Button("Refresh", id="refresh", variant="default"),
                        id="list-buttons",
                    ),
                    # Selected VM info
                    Static("Select a VM to see details", id="selected-info"),
                    # Action buttons for selected VM
                    Horizontal(
                        Button("▶ Start", id="start-vm", variant="success"),
                        Button("■ Stop", id="stop-vm", variant="error"),
                        Button("⚙ Configure", id="edit-vm", variant="default"),
                        Button("💻 Terminal", id="ssh-terminal", variant="primary"),
                        Button("🔧 Initialize", id="initialize-vm", variant="warning"),
                        Button("✗ Delete", id="remove-vm", variant="error"),
                        id="action-buttons",
                    ),
                    id="vm-list-section",
                ),
                # Right: VM Form
                Vertical(
                    VerticalScroll(
                        Static("[bold]VM Configuration[/bold]"),
                        Label("Name:"),
                        Input(placeholder="e.g., worker-1", id="vm-name"),
                        Label("Description:"),
                        Input(placeholder="Optional description", id="vm-desc"),
                        Rule(),
                        Static("[bold]Connection[/bold]"),
                        Label("IP Address / Hostname:"),
                        Horizontal(
                            Input(placeholder="192.168.1.11", id="vm-ip"),
                            Button("Pick", id="pick-ip", variant="default"),
                        ),
                        Label("SSH User:"),
                        Input(placeholder="manager", id="vm-user", value="manager"),
                        Label("SSH Port:"),
                        Input(placeholder="22", id="vm-port", value="22"),
                        Label("SSH Key Path:"),
                        Input(placeholder="Auto-generated on init", id="vm-key"),
                        Rule(),
                        Static("[bold]Classification[/bold]"),
                        Label("Type:"),
                        Select(
                            [("LXC Container", "lxc"), ("VM (QEMU)", "qemu"), ("External", "external")],
                            id="vm-type",
                            value="lxc",
                        ),
                        Label("Role:"),
                        Select(
                            [("Worker", "worker"), ("Traefik", "traefik")],
                            id="vm-role",
                            value="worker",
                        ),
                        Rule(),
                        Static("[bold]Network[/bold]"),
                        Label("Gateway:"),
                        Input(placeholder="From settings", id="vm-gateway"),
                        Label("Primary DNS:"),
                        Input(placeholder="From settings", id="vm-dns1"),
                        Rule(),
                        Static("[bold]Proxmox[/bold]"),
                        Label("VM ID:"),
                        Input(placeholder="Optional", id="vm-proxmox-id"),
                        Label("Node:"),
                        Input(placeholder="e.g., pve", id="vm-proxmox-node"),
                        id="vm-form-scroll",
                    ),
                    Horizontal(
                        Button("Save", id="save-vm", variant="success"),
                        Button("Clear", id="clear-form", variant="default"),
                        Button("Test SSH", id="test-conn", variant="primary"),
                        id="form-buttons",
                    ),
                    id="vm-form-section",
                ),
            ),
            id="main-content",
        )
        yield Vertical(
            Static("[bold]Initialization Progress[/bold]"),
            ProgressBar(total=100, id="init-progress"),
            Static("", id="init-log-output"),
            id="init-log-container",
        )
        yield Static("", id="status-message")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen."""
        vm_table = self.query_one("#vm-table", DataTable)
        vm_table.add_columns("Name", "Type", "IP", "Role", "Status", "Init")
        vm_table.cursor_type = "row"
        self.refresh_vms()

    def on_screen_resume(self) -> None:
        """Refresh when returning to this screen."""
        self.refresh_vms()

    def refresh_vms(self) -> None:
        """Refresh the VM list."""
        config_loader = get_config_loader()
        vm_table = self.query_one("#vm-table", DataTable)
        vm_table.clear()

        try:
            vms_config = config_loader.load_vms()
            for vm in vms_config.vms:
                ip = vm.network.ip_address or vm.host
                vm_type = vm.proxmox_type.upper() if vm.proxmox_type else "EXT"
                status = "●" if vm.initialized else "○"
                init_status = "[green]✓[/green]" if vm.initialized else "[red]✗[/red]"

                vm_table.add_row(
                    vm.name,
                    vm_type,
                    ip,
                    vm.role,
                    status,
                    init_status,
                )
        except Exception as e:
            self.show_status(f"Error loading VMs: {e}", "error")

    def get_selected_vm(self) -> VMConfig | None:
        """Get the currently selected VM."""
        vm_table = self.query_one("#vm-table", DataTable)
        if vm_table.cursor_row is None:
            return None

        try:
            row = vm_table.get_row_at(vm_table.cursor_row)
            vm_name = row[0]

            config_loader = get_config_loader()
            vms_config = config_loader.load_vms()
            return vms_config.get_vm_by_name(vm_name)
        except Exception:
            return None

    def update_selected_info(self) -> None:
        """Update the selected VM info display."""
        vm = self.get_selected_vm()
        info_widget = self.query_one("#selected-info", Static)

        if not vm:
            info_widget.update("Select a VM to see details")
            return

        init_text = "[green]Initialized[/green]" if vm.initialized else "[yellow]Not initialized[/yellow]"
        type_text = vm.proxmox_type.upper() if vm.proxmox_type else "External"

        info = f"[bold]{vm.name}[/bold] ({type_text}) - {vm.host} - {vm.role} - {init_text}"
        if vm.description:
            info += f"\n{vm.description}"

        info_widget.update(info)

    def clear_form(self) -> None:
        """Clear the VM form."""
        self.editing_vm = None
        config_loader = get_config_loader()
        settings = config_loader.load_settings()

        self.query_one("#vm-name", Input).value = ""
        self.query_one("#vm-desc", Input).value = ""
        self.query_one("#vm-ip", Input).value = ""
        self.query_one("#vm-user", Input).value = "manager"
        self.query_one("#vm-port", Input).value = "22"
        self.query_one("#vm-key", Input).value = ""
        self.query_one("#vm-type", Select).value = "lxc"
        self.query_one("#vm-role", Select).value = "worker"
        self.query_one("#vm-gateway", Input).value = settings.network.gateway
        self.query_one("#vm-dns1", Input).value = settings.network.dns_primary
        self.query_one("#vm-proxmox-id", Input).value = ""
        self.query_one("#vm-proxmox-node", Input).value = settings.proxmox.default_node

    def load_vm_to_form(self, vm: VMConfig) -> None:
        """Load a VM configuration into the form for editing."""
        self.editing_vm = vm.name

        self.query_one("#vm-name", Input).value = vm.name
        self.query_one("#vm-desc", Input).value = vm.description
        self.query_one("#vm-ip", Input).value = vm.network.ip_address or vm.host
        self.query_one("#vm-user", Input).value = vm.user
        self.query_one("#vm-port", Input).value = str(vm.ssh_port)
        self.query_one("#vm-key", Input).value = vm.ssh_key
        self.query_one("#vm-type", Select).value = vm.proxmox_type or "external"
        self.query_one("#vm-role", Select).value = vm.role
        self.query_one("#vm-gateway", Input).value = vm.network.gateway
        self.query_one("#vm-dns1", Input).value = vm.network.dns_primary
        self.query_one("#vm-proxmox-id", Input).value = str(vm.proxmox_vmid) if vm.proxmox_vmid else ""
        self.query_one("#vm-proxmox-node", Input).value = vm.proxmox_node

    def save_vm(self) -> None:
        """Save the VM from form data."""
        config_loader = get_config_loader()
        settings = config_loader.load_settings()

        name = self.query_one("#vm-name", Input).value.strip()
        desc = self.query_one("#vm-desc", Input).value.strip()
        ip = self.query_one("#vm-ip", Input).value.strip()
        user = self.query_one("#vm-user", Input).value.strip() or "manager"
        port = self.query_one("#vm-port", Input).value.strip() or "22"
        ssh_key = self.query_one("#vm-key", Input).value.strip()
        vm_type = self.query_one("#vm-type", Select).value
        role = self.query_one("#vm-role", Select).value
        gateway = self.query_one("#vm-gateway", Input).value.strip() or settings.network.gateway
        dns1 = self.query_one("#vm-dns1", Input).value.strip() or settings.network.dns_primary
        proxmox_id = self.query_one("#vm-proxmox-id", Input).value.strip()
        proxmox_node = self.query_one("#vm-proxmox-node", Input).value.strip()

        if not name:
            self.show_status("VM name is required", "error")
            return

        if not ip:
            self.show_status("IP address is required", "error")
            return

        vms_config = config_loader.load_vms()
        if vms_config.is_ip_used(ip, exclude_vm=self.editing_vm):
            self.show_status(f"IP address {ip} is already in use", "error")
            return

        # Warn but don't block if IP not in subnet (could be external)
        if not settings.network.is_ip_in_subnet(ip) and vm_type != "external":
            self.show_status(f"Warning: IP {ip} is not in subnet {settings.network.subnet}", "warning")

        try:
            network = VMNetworkConfig(
                ip_address=ip,
                netmask="255.255.255.0",
                gateway=gateway,
                dns_primary=dns1,
                dns_secondary=settings.network.dns_secondary,
            )

            # Preserve existing values when editing
            initialized = False
            stacks = []
            if self.editing_vm:
                old_vm = vms_config.get_vm_by_name(self.editing_vm)
                if old_vm:
                    initialized = old_vm.initialized
                    stacks = old_vm.stacks

            vm = VMConfig(
                name=name,
                host=ip,
                user=user,
                ssh_key=ssh_key,
                ssh_port=int(port),
                role=role,
                description=desc,
                network=network,
                proxmox_vmid=int(proxmox_id) if proxmox_id else 0,
                proxmox_type=vm_type,
                proxmox_node=proxmox_node,
                initialized=initialized,
                stacks=stacks,
            )

            if self.editing_vm:
                config_loader.update_vm(self.editing_vm, vm)
                self.show_status(f"VM '{name}' updated", "success")
            else:
                config_loader.add_vm(vm)
                self.show_status(f"VM '{name}' added", "success")

            self.clear_form()
            self.refresh_vms()

        except Exception as e:
            self.show_status(f"Error saving VM: {e}", "error")

    def pick_available_ip(self) -> None:
        """Pick an available IP from the subnet."""
        config_loader = get_config_loader()
        available = config_loader.get_available_ips()

        if available:
            self.query_one("#vm-ip", Input).value = available[0]
            self.show_status(f"Selected: {available[0]}", "success")
        else:
            self.show_status("No available IPs in subnet", "error")

    def add_log(self, message: str) -> None:
        """Add a log message to the initialization output."""
        self.log_messages.append(message)
        # Keep last 15 messages
        if len(self.log_messages) > 15:
            self.log_messages = self.log_messages[-15:]

        log_output = self.query_one("#init-log-output", Static)
        log_output.update("\n".join(self.log_messages))

    def _update_progress(self) -> None:
        """Update the initialization progress bar."""
        progress = self.query_one("#init-progress", ProgressBar)
        current = progress.progress or 0
        if current < 90:
            progress.update(progress=current + 8)

    def _show_init_log(self, show: bool = True) -> None:
        """Show or hide the initialization log container."""
        log_container = self.query_one("#init-log-container")
        if show:
            log_container.add_class("visible")
        else:
            log_container.remove_class("visible")

    def test_connection(self) -> None:
        """Test SSH connection to the form's VM."""
        ip = self.query_one("#vm-ip", Input).value.strip()
        user = self.query_one("#vm-user", Input).value.strip() or "manager"
        port = self.query_one("#vm-port", Input).value.strip() or "22"
        ssh_key = self.query_one("#vm-key", Input).value.strip()

        if not ip:
            self.show_status("Enter an IP address first", "error")
            return

        if not ssh_key:
            self.show_status("Enter SSH key path first", "error")
            return

        self.show_status(f"Testing connection to {ip}...")

        try:
            from pathlib import Path

            test_vm = VMConfig(
                name="test",
                host=ip,
                user=user,
                ssh_key=ssh_key,
                ssh_port=int(port),
            )

            ssh_manager = get_ssh_manager()
            success, message = ssh_manager.test_connection(test_vm)
            ssh_manager.close_connection("test")

            if success:
                self.show_status(f"Connection successful!", "success")
            else:
                self.show_status(f"Connection failed: {message}", "error")
        except Exception as e:
            self.show_status(f"Error: {e}", "error")

    def initialize_vm(self) -> None:
        """Initialize the selected VM with standard setup."""
        vm = self.get_selected_vm()
        if not vm:
            self.show_status("No VM selected", "error")
            return

        if vm.initialized:
            self.show_status(f"{vm.name} is already initialized", "warning")
            return

        if not vm.ssh_key:
            self.show_status("VM needs a root SSH key for initialization", "error")
            return

        # Store VM for worker and disable button
        self._init_vm = vm
        self.query_one("#initialize-vm", Button).disabled = True

        # Show log window and reset progress
        self.log_messages = []
        self._show_init_log(True)
        self.query_one("#init-progress", ProgressBar).update(progress=0)
        self.add_log(f"Starting initialization of {vm.name}...")
        self.show_status(f"Initializing {vm.name}... This may take several minutes.")

        # Run initialization in worker thread
        self.run_worker(
            self._initialize_worker,
            name="initialize_vm",
            thread=True,
        )

    def _initialize_worker(self) -> tuple[bool, str, str]:
        """Worker to initialize VM (runs in thread)."""
        from pathlib import Path

        vm = self._init_vm
        initializer = get_vm_initializer()

        def progress_callback(msg: str):
            self.app.call_from_thread(self.add_log, msg)
            self.app.call_from_thread(self._update_progress)

        success, manager_key_path, message = initializer.initialize_vm(
            host=vm.host,
            root_key_path=Path(vm.ssh_key),
            vm_name=vm.name,
            callback=progress_callback,
            port=vm.ssh_port,
        )

        return success, str(manager_key_path), message

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.worker.name == "initialize_vm":
            self._handle_init_worker(event)
        elif event.worker.name == "delete_vm":
            self._handle_delete_worker(event)

    def _handle_init_worker(self, event: Worker.StateChanged) -> None:
        """Handle initialization worker state."""
        self.query_one("#initialize-vm", Button).disabled = False
        self.query_one("#init-progress", ProgressBar).update(progress=100)

        if event.state == WorkerState.SUCCESS:
            success, manager_key_path, message = event.worker.result

            if success:
                config_loader = get_config_loader()
                vm = self._init_vm
                vm.user = "manager"
                vm.ssh_key = manager_key_path
                vm.initialized = True
                config_loader.update_vm(vm.name, vm)

                self.add_log("Initialization complete!")
                self.add_log(f"SSH Key (manager): {manager_key_path}")
                self.show_status(f"{vm.name} initialized successfully!", "success")
                self.notify(f"{vm.name} is ready!")
                self.refresh_vms()
            else:
                self.add_log(f"[red]Failed: {message}[/red]")
                self.show_status(f"Initialization failed: {message}", "error")

        elif event.state == WorkerState.ERROR:
            self.add_log(f"[red]Error: {event.worker.error}[/red]")
            self.show_status(f"Error: {event.worker.error}", "error")

    def _handle_delete_worker(self, event: Worker.StateChanged) -> None:
        """Handle delete worker state."""
        self.query_one("#remove-vm", Button).disabled = False

        if event.state == WorkerState.SUCCESS:
            success, message = event.worker.result

            if success:
                self.show_status(message, "success")
                self.notify(message)
                self.refresh_vms()
            else:
                self.show_status(f"Delete failed: {message}", "error")

        elif event.state == WorkerState.ERROR:
            self.show_status(f"Error: {event.worker.error}", "error")

    def remove_vm(self) -> None:
        """Remove the selected VM from config and optionally from Proxmox."""
        vm = self.get_selected_vm()
        if not vm:
            self.show_status("No VM selected", "error")
            return

        # Store for deletion worker
        self._delete_vm = vm
        self.query_one("#remove-vm", Button).disabled = True

        # Check if managed by Proxmox
        if vm.proxmox_vmid and vm.proxmox_type:
            self.show_status(f"Deleting {vm.name} from Proxmox and config...")
            self.run_worker(
                self._delete_vm_worker,
                name="delete_vm",
                thread=True,
            )
        else:
            # Just remove from config
            try:
                config_loader = get_config_loader()
                # Delete SSH keys
                from ...core.ssh_keygen import get_ssh_key_manager
                key_manager = get_ssh_key_manager()
                key_manager.delete_keypair(f"{vm.name}_root")
                key_manager.delete_keypair(f"{vm.name}_manager")

                if config_loader.remove_vm(vm.name):
                    self.refresh_vms()
                    self.show_status(f"VM '{vm.name}' removed", "success")
                else:
                    self.show_status(f"VM '{vm.name}' not found", "error")
            except Exception as e:
                self.show_status(f"Error: {e}", "error")
            finally:
                self.query_one("#remove-vm", Button).disabled = False

    def _delete_vm_worker(self) -> tuple[bool, str]:
        """Worker to delete VM from Proxmox (runs in thread)."""
        vm = self._delete_vm

        try:
            from ...core.proxmox_api import get_proxmox_api, init_proxmox_from_config
            from ...core.ssh_keygen import get_ssh_key_manager

            config_loader = get_config_loader()
            settings = config_loader.load_settings()

            # Get or initialize Proxmox API
            api = get_proxmox_api()
            if not api and settings.proxmox.enabled:
                api = init_proxmox_from_config(settings.proxmox)

            if api:
                node = vm.proxmox_node or settings.proxmox.default_node

                # Stop VM first if running
                try:
                    status = api.get_vm_status(node, vm.proxmox_vmid, vm.proxmox_type)
                    if status.get("status") == "running":
                        self.app.call_from_thread(self.show_status, f"Stopping {vm.name}...")
                        api.stop_vm(node, vm.proxmox_vmid, vm.proxmox_type)
                        import time
                        time.sleep(3)  # Wait for stop
                except Exception:
                    pass

                # Delete from Proxmox
                self.app.call_from_thread(self.show_status, f"Deleting {vm.name} from Proxmox...")
                if vm.proxmox_type == "lxc":
                    api.delete_lxc(node, vm.proxmox_vmid)
                else:
                    # For QEMU VMs - would need delete_qemu method
                    pass

            # Delete SSH keys
            key_manager = get_ssh_key_manager()
            key_manager.delete_keypair(f"{vm.name}_root")
            key_manager.delete_keypair(f"{vm.name}_manager")

            # Remove from config
            config_loader.remove_vm(vm.name)

            return True, f"{vm.name} deleted successfully"

        except Exception as e:
            return False, str(e)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "save-vm":
            self.save_vm()

        elif button_id == "clear-form":
            self.clear_form()
            self.show_status("Form cleared")

        elif button_id == "edit-vm":
            vm = self.get_selected_vm()
            if vm:
                self.load_vm_to_form(vm)
                self.show_status(f"Editing: {vm.name}")
            else:
                self.show_status("No VM selected", "error")

        elif button_id == "remove-vm":
            self.remove_vm()

        elif button_id == "test-conn":
            self.test_connection()

        elif button_id == "pick-ip":
            self.pick_available_ip()

        elif button_id == "create-lxc":
            self.app.push_screen("lxc_create")

        elif button_id == "add-existing":
            # For now, just clear form to add manually
            self.clear_form()
            self.show_status("Fill in the form to add an existing VM")

        elif button_id == "refresh":
            self.refresh_vms()
            self.show_status("Refreshed")

        elif button_id == "initialize-vm":
            self.initialize_vm()

        elif button_id == "start-vm":
            self.start_stop_vm(start=True)

        elif button_id == "stop-vm":
            self.start_stop_vm(start=False)

        elif button_id == "ssh-terminal":
            self.open_ssh_terminal()

    def _get_proxmox_api(self):
        """Get initialized Proxmox API from settings."""
        from ...core.proxmox_api import get_proxmox_api, init_proxmox_from_config

        api = get_proxmox_api()
        if not api:
            # Initialize from settings
            config_loader = get_config_loader()
            settings = config_loader.load_settings()
            if settings.proxmox.enabled:
                api = init_proxmox_from_config(settings.proxmox)
        return api

    def start_stop_vm(self, start: bool = True) -> None:
        """Start or stop the selected VM via Proxmox API."""
        vm = self.get_selected_vm()
        if not vm:
            self.show_status("No VM selected", "error")
            return

        if not vm.proxmox_vmid or not vm.proxmox_type:
            self.show_status("VM is not managed by Proxmox", "error")
            return

        action = "Starting" if start else "Stopping"
        self.show_status(f"{action} {vm.name}...")

        try:
            api = self._get_proxmox_api()
            if not api:
                self.show_status("Proxmox not configured. Check Settings.", "error")
                return

            config_loader = get_config_loader()
            settings = config_loader.load_settings()
            node = vm.proxmox_node or settings.proxmox.default_node

            if start:
                api.start_vm(node, vm.proxmox_vmid, vm.proxmox_type)
            else:
                api.stop_vm(node, vm.proxmox_vmid, vm.proxmox_type)

            done = "started" if start else "stopped"
            self.show_status(f"{vm.name} {done}", "success")

        except Exception as e:
            self.show_status(f"Error: {e}", "error")

    def open_ssh_terminal(self) -> None:
        """Open SSH terminal to the selected VM."""
        vm = self.get_selected_vm()
        if not vm:
            self.show_status("No VM selected", "error")
            return

        if not vm.initialized and vm.user != "root":
            self.show_status("VM not initialized. Initialize first or use root.", "warning")

        if not vm.ssh_key:
            self.show_status("No SSH key configured for this VM", "error")
            return

        # Build SSH command
        ssh_cmd = [
            "ssh",
            "-i", vm.ssh_key,
            "-p", str(vm.ssh_port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"{vm.user}@{vm.host}"
        ]

        self.show_status(f"Opening terminal to {vm.name}...")

        # Suspend app and run SSH
        import subprocess
        import os

        with self.app.suspend():
            # Clear screen and show connection info
            os.system("clear")
            print(f"\n  Connecting to {vm.name} ({vm.user}@{vm.host})...\n")
            print(f"  Press Ctrl+D or type 'exit' to return to the app.\n")
            print("-" * 60 + "\n")

            try:
                subprocess.run(ssh_cmd)
            except Exception as e:
                print(f"\n  Error: {e}\n")
                input("  Press Enter to continue...")

            print("\n" + "-" * 60)
            print("  Returning to Docker Stack Manager...")

        self.show_status(f"Returned from {vm.name}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the VM table."""
        self.update_selected_info()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlight changes."""
        self.update_selected_info()
