"""VM Manager screen for adding and managing VMs."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Rule,
    Select,
    Static,
)

from ...core.config_loader import VMConfig, VMNetworkConfig, get_config_loader
from ...core.ssh_manager import get_ssh_manager
from ...core.docker_manager import get_docker_manager


class VMManagerScreen(Screen):
    """Screen for managing VMs."""

    def __init__(self):
        super().__init__()
        self.editing_vm = None

    def compose(self) -> ComposeResult:
        """Compose the VM manager screen."""
        yield Container(
            Static("VM Manager", classes="title"),
            Horizontal(
                Vertical(
                    Static("Registered VMs", classes="title"),
                    DataTable(id="vm-table"),
                    Horizontal(
                        Button("Test Connection", id="test-conn", variant="primary"),
                        Button("Install Docker", id="install-docker", variant="warning"),
                        Button("Edit VM", id="edit-vm", variant="default"),
                        Button("Remove VM", id="remove-vm", variant="error"),
                    ),
                    Horizontal(
                        Button("Create LXC Container", id="create-lxc", variant="success"),
                    ),
                    classes="box",
                    id="vm-list-section",
                ),
                Vertical(
                    VerticalScroll(
                        Static("[bold]VM Information[/bold]"),
                        Label("Name:"),
                        Input(placeholder="e.g., worker-1", id="vm-name"),
                        Label("Description:"),
                        Input(placeholder="Optional description", id="vm-desc"),
                        Rule(),
                        Static("[bold]SSH Configuration[/bold]"),
                        Label("SSH User:"),
                        Input(placeholder="root", id="vm-user", value="root"),
                        Label("SSH Port:"),
                        Input(placeholder="22", id="vm-port", value="22"),
                        Label("SSH Key Path:"),
                        Input(placeholder="~/.ssh/id_rsa", id="vm-key", value="~/.ssh/id_rsa"),
                        Rule(),
                        Static("[bold]Role[/bold]"),
                        Label("VM Role:"),
                        Select(
                            [("Worker", "worker"), ("Traefik", "traefik"), ("Manager", "manager")],
                            id="vm-role",
                            value="worker",
                        ),
                        Rule(),
                        Static("[bold]Network Configuration[/bold]"),
                        Label("IP Address:"),
                        Horizontal(
                            Input(placeholder="192.168.1.11", id="vm-ip"),
                            Button("Pick Available", id="pick-ip", variant="default"),
                            id="ip-row",
                        ),
                        Label("Netmask:"),
                        Input(placeholder="255.255.255.0", id="vm-netmask", value="255.255.255.0"),
                        Label("Gateway:"),
                        Input(placeholder="Will use default from settings", id="vm-gateway"),
                        Rule(),
                        Static("[bold]DNS Configuration[/bold]"),
                        Label("Primary DNS:"),
                        Input(placeholder="Will use default from settings", id="vm-dns1"),
                        Label("Secondary DNS:"),
                        Input(placeholder="Will use default from settings", id="vm-dns2"),
                        Rule(),
                        Static("[bold]Optional[/bold]"),
                        Label("MAC Address:"),
                        Input(placeholder="AA:BB:CC:DD:EE:FF", id="vm-mac"),
                        Label("Proxmox VM ID:"),
                        Input(placeholder="Optional", id="vm-proxmox-id"),
                        id="vm-form-scroll",
                    ),
                    Horizontal(
                        Button("Save VM", id="save-vm", variant="success"),
                        Button("Clear Form", id="clear-form", variant="default"),
                    ),
                    classes="box",
                    id="vm-form-section",
                ),
            ),
            Static("", id="status-message"),
            id="main-content",
        )

    def on_mount(self) -> None:
        """Initialize the screen."""
        # Setup VM table
        vm_table = self.query_one("#vm-table", DataTable)
        vm_table.add_columns("Name", "IP Address", "Role", "Status")
        vm_table.cursor_type = "row"

        # Load VMs
        self.refresh_vms()

    def refresh_vms(self) -> None:
        """Refresh the VM list."""
        config_loader = get_config_loader()
        ssh_manager = get_ssh_manager()
        vm_table = self.query_one("#vm-table", DataTable)
        vm_table.clear()

        try:
            vms_config = config_loader.load_vms()
            for vm in vms_config.vms:
                # Get IP display
                ip = vm.network.ip_address or vm.host

                # Quick status check (without actually connecting)
                status = "Unknown"

                vm_table.add_row(
                    vm.name,
                    ip,
                    vm.role,
                    status,
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

    def show_status(self, message: str, level: str = "info") -> None:
        """Show a status message."""
        status = self.query_one("#status-message", Static)
        if level == "error":
            status.update(f"[red]{message}[/red]")
        elif level == "success":
            status.update(f"[green]{message}[/green]")
        else:
            status.update(message)

    def clear_form(self) -> None:
        """Clear the VM form."""
        self.editing_vm = None

        # Basic tab
        self.query_one("#vm-name", Input).value = ""
        self.query_one("#vm-desc", Input).value = ""
        self.query_one("#vm-user", Input).value = "root"
        self.query_one("#vm-port", Input).value = "22"
        self.query_one("#vm-key", Input).value = "~/.ssh/id_rsa"
        self.query_one("#vm-role", Select).value = "worker"

        # Network tab
        self.query_one("#vm-ip", Input).value = ""
        self.query_one("#vm-netmask", Input).value = "255.255.255.0"
        self.query_one("#vm-gateway", Input).value = ""
        self.query_one("#vm-dns1", Input).value = ""
        self.query_one("#vm-dns2", Input).value = ""
        self.query_one("#vm-mac", Input).value = ""
        self.query_one("#vm-proxmox-id", Input).value = ""

    def load_vm_to_form(self, vm: VMConfig) -> None:
        """Load a VM configuration into the form for editing."""
        self.editing_vm = vm.name

        # Basic tab
        self.query_one("#vm-name", Input).value = vm.name
        self.query_one("#vm-desc", Input).value = vm.description
        self.query_one("#vm-user", Input).value = vm.user
        self.query_one("#vm-port", Input).value = str(vm.ssh_port)
        self.query_one("#vm-key", Input).value = vm.ssh_key
        self.query_one("#vm-role", Select).value = vm.role

        # Network tab
        self.query_one("#vm-ip", Input).value = vm.network.ip_address or vm.host
        self.query_one("#vm-netmask", Input).value = vm.network.netmask
        self.query_one("#vm-gateway", Input).value = vm.network.gateway
        self.query_one("#vm-dns1", Input).value = vm.network.dns_primary
        self.query_one("#vm-dns2", Input).value = vm.network.dns_secondary
        self.query_one("#vm-mac", Input).value = vm.network.mac_address
        self.query_one("#vm-proxmox-id", Input).value = str(vm.proxmox_vmid) if vm.proxmox_vmid else ""

    def save_vm(self) -> None:
        """Save the VM from form data."""
        config_loader = get_config_loader()
        settings = config_loader.load_settings()

        # Get form values
        name = self.query_one("#vm-name", Input).value.strip()
        desc = self.query_one("#vm-desc", Input).value.strip()
        user = self.query_one("#vm-user", Input).value.strip() or "root"
        port = self.query_one("#vm-port", Input).value.strip() or "22"
        ssh_key = self.query_one("#vm-key", Input).value.strip() or "~/.ssh/id_rsa"
        role = self.query_one("#vm-role", Select).value

        ip = self.query_one("#vm-ip", Input).value.strip()
        netmask = self.query_one("#vm-netmask", Input).value.strip() or "255.255.255.0"
        gateway = self.query_one("#vm-gateway", Input).value.strip() or settings.network.gateway
        dns1 = self.query_one("#vm-dns1", Input).value.strip() or settings.network.dns_primary
        dns2 = self.query_one("#vm-dns2", Input).value.strip() or settings.network.dns_secondary
        mac = self.query_one("#vm-mac", Input).value.strip()
        proxmox_id = self.query_one("#vm-proxmox-id", Input).value.strip()

        # Validation
        if not name:
            self.show_status("VM name is required", "error")
            return

        if not ip:
            self.show_status("IP address is required", "error")
            return

        # Check if IP is already used (unless editing same VM)
        vms_config = config_loader.load_vms()
        if vms_config.is_ip_used(ip, exclude_vm=self.editing_vm):
            self.show_status(f"IP address {ip} is already in use", "error")
            return

        # Check if IP is in configured subnet
        if not settings.network.is_ip_in_subnet(ip):
            self.show_status(f"IP {ip} is not in subnet {settings.network.subnet}", "error")
            return

        try:
            network = VMNetworkConfig(
                ip_address=ip,
                netmask=netmask,
                gateway=gateway,
                dns_primary=dns1,
                dns_secondary=dns2,
                mac_address=mac,
            )

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
                stacks=[],  # Will be preserved if editing
            )

            if self.editing_vm:
                # Preserve stacks when editing
                old_vm = vms_config.get_vm_by_name(self.editing_vm)
                if old_vm:
                    vm.stacks = old_vm.stacks

                config_loader.update_vm(self.editing_vm, vm)
                self.show_status(f"VM '{name}' updated successfully", "success")
            else:
                config_loader.add_vm(vm)
                self.show_status(f"VM '{name}' added successfully", "success")

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
            self.show_status(f"Selected available IP: {available[0]}", "success")
        else:
            self.show_status("No available IPs in subnet", "error")

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
                self.show_status(f"Editing VM: {vm.name}")
            else:
                self.show_status("No VM selected", "error")

        elif button_id == "remove-vm":
            self.remove_vm()

        elif button_id == "test-conn":
            self.test_connection()

        elif button_id == "install-docker":
            self.install_docker()

        elif button_id == "pick-ip":
            self.pick_available_ip()

        elif button_id == "create-lxc":
            self.app.push_screen("lxc_create")

    def remove_vm(self) -> None:
        """Remove the selected VM."""
        vm = self.get_selected_vm()
        if not vm:
            self.show_status("No VM selected", "error")
            return

        try:
            config_loader = get_config_loader()
            if config_loader.remove_vm(vm.name):
                self.refresh_vms()
                self.show_status(f"VM '{vm.name}' removed", "success")
            else:
                self.show_status(f"VM '{vm.name}' not found", "error")
        except Exception as e:
            self.show_status(f"Error removing VM: {e}", "error")

    def test_connection(self) -> None:
        """Test connection to the selected VM."""
        vm = self.get_selected_vm()
        if not vm:
            self.show_status("No VM selected", "error")
            return

        self.show_status(f"Testing connection to {vm.name}...")

        try:
            ssh_manager = get_ssh_manager()
            success, message = ssh_manager.test_connection(vm)

            if success:
                self.show_status(f"Connection to {vm.name} successful!", "success")
                # Update status in table
                self.refresh_vms()
            else:
                self.show_status(f"Connection failed: {message}", "error")
        except Exception as e:
            self.show_status(f"Error: {e}", "error")

    def install_docker(self) -> None:
        """Install Docker on the selected VM."""
        vm = self.get_selected_vm()
        if not vm:
            self.show_status("No VM selected", "error")
            return

        self.show_status(f"Installing Docker on {vm.name}... This may take a while.")

        try:
            docker_manager = get_docker_manager()

            # Check if already installed
            if docker_manager.is_docker_installed(vm):
                version = docker_manager.get_docker_version(vm)
                self.show_status(f"Docker already installed: {version}", "success")
                return

            # Install Docker
            success, message = docker_manager.install_docker(vm)

            if success:
                self.show_status(f"Docker installed on {vm.name}!", "success")
            else:
                self.show_status(f"Installation failed: {message}", "error")

        except Exception as e:
            self.show_status(f"Error: {e}", "error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the VM table."""
        # Could auto-load VM details here if desired
        pass
