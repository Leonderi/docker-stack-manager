"""Stack deployment screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Input,
    Label,
    ListView,
    ListItem,
    RichLog,
    Select,
    Static,
)

from ..base_screen import BaseScreen
from ...core.config_loader import get_config_loader
from ...stacks.base import get_available_stacks, get_stack, StackConfig


class StackDeployScreen(BaseScreen):
    """Screen for deploying stacks."""

    def __init__(self):
        super().__init__()
        self.selected_stack = None
        self.env_inputs = {}

    def compose(self) -> ComposeResult:
        """Compose the stack deploy screen."""
        yield Container(
            Static("Stack Deployment", classes="title"),
            Horizontal(
                Vertical(
                    Static("Available Stacks", classes="title"),
                    ListView(id="stack-list"),
                    Static("", id="stack-description"),
                    classes="box",
                    id="stack-selection",
                ),
                Vertical(
                    Static("Deployment Configuration", classes="title"),
                    Label("Target VM:"),
                    Select(id="target-vm", options=[]),
                    Label("Subdomain:"),
                    Input(placeholder="e.g., grafana", id="subdomain"),
                    Static("Environment Variables:", classes="title"),
                    VerticalScroll(id="env-vars"),
                    classes="box",
                    id="deploy-form",
                ),
            ),
            Horizontal(
                Button("Deploy Stack", id="deploy", variant="success"),
                Button("Remove Stack", id="undeploy", variant="error"),
                id="action-buttons",
            ),
            RichLog(id="deploy-log", highlight=True, markup=True),
            id="main-content",
        )

    def on_mount(self) -> None:
        """Initialize the screen."""
        self.populate_stacks()
        self.populate_vms()

    def populate_stacks(self) -> None:
        """Populate the stack list."""
        stack_list = self.query_one("#stack-list", ListView)
        stack_list.clear()

        stacks = get_available_stacks()
        for name, info in stacks.items():
            stack_list.append(
                ListItem(Label(f"{info.display_name}"), id=f"stack-{name}")
            )

    def populate_vms(self, role_filter: str = "worker") -> None:
        """Populate the VM selector based on role filter."""
        config_loader = get_config_loader()
        vm_select = self.query_one("#target-vm", Select)

        try:
            vms_config = config_loader.load_vms()
            options = [
                (vm.name, vm.name)
                for vm in vms_config.vms
                if vm.role == role_filter
            ]

            vm_select.set_options(options)
            if options:
                vm_select.value = options[0][1]
            else:
                vm_select.set_options([])

        except Exception as e:
            self.log_message(f"Error loading VMs: {e}", "error")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle stack selection."""
        if event.item and event.item.id:
            stack_name = event.item.id.replace("stack-", "")
            self.select_stack(stack_name)

    def select_stack(self, stack_name: str) -> None:
        """Select a stack and show its configuration."""
        self.selected_stack = stack_name
        stack = get_stack(stack_name)

        if not stack:
            return

        info = stack.info

        # Update VM list based on stack type
        if stack_name == "traefik":
            self.populate_vms("traefik")
        else:
            self.populate_vms("worker")

        # Update description
        desc_widget = self.query_one("#stack-description", Static)
        desc_widget.update(
            f"[bold]{info.display_name}[/bold]\n"
            f"{info.description}\n"
            f"Default port: {info.default_port}"
        )

        # Update subdomain suggestion (not needed for Traefik)
        subdomain_input = self.query_one("#subdomain", Input)
        if stack_name == "traefik":
            subdomain_input.value = ""
            subdomain_input.disabled = True
        else:
            subdomain_input.value = stack_name
            subdomain_input.disabled = False

        # Create env var inputs
        env_container = self.query_one("#env-vars", VerticalScroll)
        env_container.remove_children()
        self.env_inputs = {}

        # Required env vars
        if info.required_env_vars:
            env_container.mount(Static("[bold]Required:[/bold]"))
            for var in info.required_env_vars:
                env_container.mount(Label(var))
                input_widget = Input(placeholder=f"Enter {var}", id=f"env-{var}")
                env_container.mount(input_widget)
                self.env_inputs[var] = input_widget

        # Optional env vars
        if info.optional_env_vars:
            env_container.mount(Static("[bold]Optional:[/bold]"))
            for var, default in info.optional_env_vars.items():
                env_container.mount(Label(f"{var} (default: {default})"))
                input_widget = Input(value=default, id=f"env-{var}")
                env_container.mount(input_widget)
                self.env_inputs[var] = input_widget

        # Show message if no env vars
        if not info.required_env_vars and not info.optional_env_vars:
            env_container.mount(Static("[dim]No configuration needed[/dim]"))

    def log_message(self, message: str, level: str = "info") -> None:
        """Log a message to the deploy log."""
        log = self.query_one("#deploy-log", RichLog)
        if level == "error":
            log.write(f"[red]ERROR: {message}[/red]")
        elif level == "success":
            log.write(f"[green]SUCCESS: {message}[/green]")
        elif level == "warning":
            log.write(f"[yellow]WARNING: {message}[/yellow]")
        else:
            log.write(f"INFO: {message}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "deploy":
            self.deploy_stack()
        elif event.button.id == "undeploy":
            self.undeploy_stack()

    def deploy_stack(self) -> None:
        """Deploy the selected stack."""
        if not self.selected_stack:
            self.log_message("No stack selected", "error")
            return

        vm_name = self.query_one("#target-vm", Select).value
        if not vm_name:
            self.log_message("No target VM selected", "error")
            return

        subdomain = self.query_one("#subdomain", Input).value.strip()
        # Subdomain not required for Traefik
        if not subdomain and self.selected_stack != "traefik":
            self.log_message("Subdomain is required", "error")
            return

        # Collect env vars
        env_vars = {}
        for var, input_widget in self.env_inputs.items():
            value = input_widget.value.strip()
            if value:
                env_vars[var] = value

        # Get VM and stack
        config_loader = get_config_loader()
        vms_config = config_loader.load_vms()
        vm = vms_config.get_vm_by_name(vm_name)

        if not vm:
            self.log_message(f"VM '{vm_name}' not found", "error")
            return

        stack = get_stack(self.selected_stack)
        if not stack:
            self.log_message(f"Stack '{self.selected_stack}' not found", "error")
            return

        # Create config
        config = StackConfig(
            subdomain=subdomain,
            env_vars=env_vars,
        )

        # Validate
        valid, msg = stack.validate_config(config)
        if not valid:
            self.log_message(msg, "error")
            return

        # Deploy
        self.log_message(f"Deploying {self.selected_stack} to {vm_name}...")

        try:
            success, message = stack.deploy(vm, config)

            if success:
                self.log_message(message, "success")
                self.notify(f"Stack deployed: {subdomain}")
            else:
                self.log_message(f"Deployment failed: {message}", "error")

        except Exception as e:
            self.log_message(f"Error: {e}", "error")

    def undeploy_stack(self) -> None:
        """Remove the selected stack."""
        if not self.selected_stack:
            self.log_message("No stack selected", "error")
            return

        vm_name = self.query_one("#target-vm", Select).value
        if not vm_name:
            self.log_message("No target VM selected", "error")
            return

        config_loader = get_config_loader()
        vms_config = config_loader.load_vms()
        vm = vms_config.get_vm_by_name(vm_name)

        if not vm:
            self.log_message(f"VM '{vm_name}' not found", "error")
            return

        stack = get_stack(self.selected_stack)
        if not stack:
            self.log_message(f"Stack '{self.selected_stack}' not found", "error")
            return

        self.log_message(f"Removing {self.selected_stack} from {vm_name}...")

        try:
            success, message = stack.undeploy(vm, remove_data=False)

            if success:
                self.log_message(message, "success")
                self.notify(f"Stack removed: {self.selected_stack}")
            else:
                self.log_message(f"Removal failed: {message}", "error")

        except Exception as e:
            self.log_message(f"Error: {e}", "error")
