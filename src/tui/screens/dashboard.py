"""Dashboard screen showing overview of VMs and stacks."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static

from ...core.config_loader import get_config_loader
from ...core.ssh_manager import get_ssh_manager
from ...core.docker_manager import get_docker_manager
from ...core.traefik_manager import get_traefik_manager


class DashboardScreen(Screen):
    """Main dashboard showing system overview."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the dashboard screen."""
        yield Container(
            Horizontal(
                Static("Dashboard", classes="title"),
                Button("Settings", id="settings-btn", variant="default"),
                id="header-row",
            ),
            Horizontal(
                Vertical(
                    Static("Virtual Machines", classes="title"),
                    DataTable(id="vm-table"),
                    Horizontal(
                        Button("Manage VMs", id="manage-vms", variant="primary"),
                        Button("Refresh", id="refresh-vms", variant="default"),
                    ),
                    classes="box",
                    id="vm-section",
                ),
                Vertical(
                    Static("Traefik Status", classes="title"),
                    Static("Loading...", id="traefik-status"),
                    Static("", id="traefik-routes"),
                    Horizontal(
                        Button("Deploy Traefik", id="deploy-traefik", variant="success"),
                        Button("View Logs", id="traefik-logs", variant="default"),
                    ),
                    classes="box",
                    id="traefik-section",
                ),
                id="top-row",
            ),
            Horizontal(
                Vertical(
                    Static("Network Info", classes="title"),
                    Static("", id="network-info"),
                    classes="box",
                    id="network-section",
                ),
                Vertical(
                    Static("Quick Stats", classes="title"),
                    Static("", id="quick-stats"),
                    classes="box",
                    id="stats-section",
                ),
                id="middle-row",
            ),
            Vertical(
                Static("Deployed Stacks", classes="title"),
                DataTable(id="stacks-table"),
                Horizontal(
                    Button("Deploy Stack", id="deploy-stack", variant="success"),
                    Button("Refresh Stacks", id="refresh-stacks", variant="default"),
                ),
                classes="box",
                id="stacks-section",
            ),
            id="main-content",
        )

    def on_mount(self) -> None:
        """Initialize tables and load data."""
        # Setup VM table
        vm_table = self.query_one("#vm-table", DataTable)
        vm_table.add_columns("Name", "IP", "Role", "Docker")

        # Setup stacks table
        stacks_table = self.query_one("#stacks-table", DataTable)
        stacks_table.add_columns("Stack", "VM", "Status", "URL")

        # Load data
        self.action_refresh()

    def action_refresh(self) -> None:
        """Refresh all data."""
        self.refresh_network_info()
        self.refresh_vms()
        self.refresh_traefik()
        self.refresh_stacks()
        self.refresh_stats()

    def refresh_network_info(self) -> None:
        """Refresh network information."""
        config_loader = get_config_loader()
        network_widget = self.query_one("#network-info", Static)

        try:
            settings = config_loader.load_settings()
            net = settings.network

            info = (
                f"Subnet: {net.subnet}\n"
                f"Gateway: {net.gateway}\n"
                f"DNS: {net.dns_primary}, {net.dns_secondary}\n"
                f"Domain: {settings.domain or 'Not configured'}"
            )
            network_widget.update(info)

        except Exception as e:
            network_widget.update(f"[red]Error: {e}[/red]")

    def refresh_stats(self) -> None:
        """Refresh quick stats."""
        config_loader = get_config_loader()
        stats_widget = self.query_one("#quick-stats", Static)

        try:
            vms = config_loader.load_vms()
            settings = config_loader.load_settings()

            total_vms = len(vms.vms)
            traefik_vms = len([v for v in vms.vms if v.role == "traefik"])
            worker_vms = len([v for v in vms.vms if v.role == "worker"])
            total_stacks = sum(len(v.stacks) for v in vms.vms)
            available_ips = len(config_loader.get_available_ips())

            stats = (
                f"VMs: {total_vms} ({traefik_vms} Traefik, {worker_vms} Worker)\n"
                f"Deployed Stacks: {total_stacks}\n"
                f"Available IPs: {available_ips}\n"
                f"SSL: {'Staging' if settings.ssl.staging else 'Production'}"
            )
            stats_widget.update(stats)

        except Exception as e:
            stats_widget.update(f"[red]Error: {e}[/red]")

    def refresh_vms(self) -> None:
        """Refresh VM status."""
        config_loader = get_config_loader()
        docker_manager = get_docker_manager()

        vm_table = self.query_one("#vm-table", DataTable)
        vm_table.clear()

        try:
            vms_config = config_loader.load_vms()
            for vm in vms_config.vms:
                # Get IP
                ip = vm.network.ip_address or vm.host

                # Check Docker (quick check without SSH)
                docker_status = "Unknown"

                vm_table.add_row(
                    vm.name,
                    ip,
                    vm.role,
                    docker_status,
                )
        except Exception as e:
            self.notify(f"Error loading VMs: {e}", severity="error")

    def refresh_traefik(self) -> None:
        """Refresh Traefik status."""
        config_loader = get_config_loader()

        status_widget = self.query_one("#traefik-status", Static)
        routes_widget = self.query_one("#traefik-routes", Static)

        try:
            vms = config_loader.load_vms()
            traefik_vm = vms.get_traefik_vm()

            if not traefik_vm:
                status_widget.update("[yellow]No Traefik VM configured[/yellow]")
                routes_widget.update("Add a VM with role 'traefik' first")
                return

            # Try to get Traefik status
            try:
                traefik_manager = get_traefik_manager()
                running, status = traefik_manager.get_traefik_status()

                if running:
                    status_widget.update(f"[green]Running[/green] on {traefik_vm.host}")
                else:
                    status_widget.update(f"[red]Not running[/red]: {status}")

                # Get routes
                routes = traefik_manager.list_routes()
                settings = config_loader.load_settings()
                if routes:
                    route_list = "\n".join(f"  - {r}.{settings.domain}" for r in routes)
                    routes_widget.update(f"Active routes:\n{route_list}")
                else:
                    routes_widget.update("No routes configured")

            except Exception as e:
                status_widget.update(f"[yellow]Cannot connect[/yellow]: {traefik_vm.host}")
                routes_widget.update("Check VM connectivity")

        except Exception as e:
            status_widget.update(f"[red]Error[/red]: {e}")
            routes_widget.update("")

    def refresh_stacks(self) -> None:
        """Refresh deployed stacks."""
        config_loader = get_config_loader()

        stacks_table = self.query_one("#stacks-table", DataTable)
        stacks_table.clear()

        try:
            vms_config = config_loader.load_vms()
            settings = config_loader.load_settings()

            for vm in vms_config.vms:
                for stack_name in vm.stacks:
                    url = f"https://{stack_name}.{settings.domain}"

                    stacks_table.add_row(
                        stack_name,
                        vm.name,
                        "Deployed",
                        url,
                    )

        except Exception as e:
            self.notify(f"Error loading stacks: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "refresh-vms":
            self.refresh_vms()
            self.notify("VMs refreshed")

        elif button_id == "refresh-stacks":
            self.refresh_stacks()
            self.notify("Stacks refreshed")

        elif button_id == "deploy-stack":
            self.app.push_screen("stacks")

        elif button_id == "traefik-logs":
            self.app.push_screen("logs")

        elif button_id == "manage-vms":
            self.app.push_screen("vms")

        elif button_id == "settings-btn":
            self.app.push_screen("settings")

        elif button_id == "deploy-traefik":
            self.deploy_traefik()

    def deploy_traefik(self) -> None:
        """Deploy Traefik to the Traefik VM."""
        config_loader = get_config_loader()
        vms = config_loader.load_vms()
        traefik_vm = vms.get_traefik_vm()

        if not traefik_vm:
            self.notify("No Traefik VM configured. Add one in VM Manager.", severity="error")
            return

        self.notify(f"Deploying Traefik to {traefik_vm.name}...")

        try:
            traefik_manager = get_traefik_manager()
            success, message = traefik_manager.deploy_traefik()

            if success:
                self.notify("Traefik deployed successfully!", severity="information")
                self.refresh_traefik()
            else:
                self.notify(f"Deployment failed: {message}", severity="error")

        except Exception as e:
            self.notify(f"Error: {e}", severity="error")
