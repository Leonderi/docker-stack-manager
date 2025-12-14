"""Dashboard screen showing overview of VMs and stacks."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Static

from ..base_screen import BaseScreen
from ...core.config_loader import get_config_loader
from ...core.docker_manager import get_docker_manager
from ...core.traefik_manager import get_traefik_manager


class DashboardScreen(BaseScreen):
    """Main dashboard showing system overview."""

    CSS = """
    DashboardScreen {
        layout: vertical;
        height: 100%;
    }

    #dashboard-title {
        width: 100%;
        height: auto;
        content-align: center middle;
        text-style: bold;
        color: $primary;
        padding: 0;
    }

    #dashboard-content {
        height: 1fr;
        width: 100%;
    }

    DashboardScreen VerticalScroll {
        height: 1fr;
        max-height: 100%;
    }

    #vm-section {
        width: 100%;
        height: auto;
        min-height: 8;
    }

    #info-row {
        height: auto;
        min-height: 6;
    }

    #info-row > Vertical {
        width: 1fr;
        height: auto;
    }

    #stacks-section {
        height: auto;
        min-height: 6;
    }

    .box {
        border: solid $primary;
        margin: 0 1 1 1;
        padding: 1;
    }

    #action-buttons {
        dock: bottom;
        height: auto;
        padding: 1;
        align: center middle;
        background: $surface;
    }

    #action-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
    ]

    TITLE_ASCII = """[bold cyan]
 ██████╗  █████╗ ███████╗██╗  ██╗██████╗  ██████╗  █████╗ ██████╗ ██████╗
 ██╔══██╗██╔══██╗██╔════╝██║  ██║██╔══██╗██╔═══██╗██╔══██╗██╔══██╗██╔══██╗
 ██║  ██║███████║███████╗███████║██████╔╝██║   ██║███████║██████╔╝██║  ██║
 ██║  ██║██╔══██║╚════██║██╔══██║██╔══██╗██║   ██║██╔══██║██╔══██╗██║  ██║
 ██████╔╝██║  ██║███████║██║  ██║██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝
 ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝
[/bold cyan]"""

    def compose(self) -> ComposeResult:
        """Compose the dashboard screen."""
        yield Static(self.TITLE_ASCII.strip(), id="dashboard-title")
        yield VerticalScroll(
            # VM Section - Full Width
            Vertical(
                Static("[bold]Virtual Machines[/bold]"),
                DataTable(id="vm-table"),
                classes="box",
                id="vm-section",
            ),
            # Info Row - Traefik + Stats side by side
            Horizontal(
                Vertical(
                    Static("[bold]Traefik Status[/bold]"),
                    Static("Loading...", id="traefik-status"),
                    Static("", id="traefik-routes"),
                    classes="box",
                    id="traefik-section",
                ),
                Vertical(
                    Static("[bold]Network & Stats[/bold]"),
                    Static("", id="network-info"),
                    Static("", id="quick-stats"),
                    classes="box",
                    id="stats-section",
                ),
                id="info-row",
            ),
            # Stacks Section
            Vertical(
                Static("[bold]Deployed Stacks[/bold]"),
                DataTable(id="stacks-table"),
                classes="box",
                id="stacks-section",
            ),
            id="dashboard-content",
        )
        # Action buttons at bottom
        yield Horizontal(
            Button("Settings", id="btn-settings", variant="default"),
            Button("Manage VMs", id="btn-vms", variant="primary"),
            Button("Deploy Stack", id="btn-stacks", variant="success"),
            Button("View Logs", id="btn-logs", variant="default"),
            Button("Refresh", id="btn-refresh", variant="default"),
            id="action-buttons",
        )
        yield Footer()

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

    def on_screen_resume(self) -> None:
        """Refresh data when returning to dashboard from another screen."""
        # Reload settings in case they changed
        config_loader = get_config_loader()
        config_loader.load_settings(reload=True)
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

            except Exception:
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

        if button_id == "btn-settings":
            self.app.push_screen("settings")

        elif button_id == "btn-vms":
            self.app.push_screen("vms")

        elif button_id == "btn-stacks":
            self.app.push_screen("stacks")

        elif button_id == "btn-logs":
            self.app.push_screen("logs")

        elif button_id == "btn-refresh":
            self.action_refresh()
            self.notify("Dashboard refreshed")

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
