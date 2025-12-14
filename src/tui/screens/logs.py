"""Log viewer screen."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, RichLog, Select, Static

from ..base_screen import BaseScreen
from ...core.config_loader import get_config_loader
from ...core.docker_manager import get_docker_manager
from ...core.traefik_manager import get_traefik_manager
from ...stacks.base import get_available_stacks, get_stack


class LogViewerScreen(BaseScreen):
    """Screen for viewing logs."""

    BINDINGS = [
        ("r", "refresh_logs", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the log viewer screen."""
        yield Container(
            Static("Log Viewer", classes="title"),
            Horizontal(
                Select(
                    [("Traefik", "traefik")],
                    id="log-source",
                    value="traefik",
                ),
                Select(
                    [
                        ("50 lines", "50"),
                        ("100 lines", "100"),
                        ("200 lines", "200"),
                        ("500 lines", "500"),
                    ],
                    id="log-lines",
                    value="100",
                ),
                Button("Refresh", id="refresh", variant="primary"),
                Button("Clear", id="clear", variant="warning"),
                id="controls",
            ),
            Container(
                RichLog(id="log-output", highlight=True, markup=True),
                id="log-container",
            ),
            id="main-content",
        )

    def on_mount(self) -> None:
        """Initialize the screen."""
        self.populate_log_sources()
        self.action_refresh_logs()

    def populate_log_sources(self) -> None:
        """Populate log source options."""
        config_loader = get_config_loader()
        log_source = self.query_one("#log-source", Select)

        options = [("Traefik", "traefik")]

        try:
            vms_config = config_loader.load_vms()

            # Add deployed stacks
            for vm in vms_config.vms:
                if vm.role == "worker":
                    for stack_name in vm.stacks:
                        options.append(
                            (f"{stack_name} ({vm.name})", f"{stack_name}:{vm.name}")
                        )

            log_source.set_options(options)

        except Exception:
            pass

    def action_refresh_logs(self) -> None:
        """Refresh the logs."""
        log_source = self.query_one("#log-source", Select).value
        lines = int(self.query_one("#log-lines", Select).value)
        log_output = self.query_one("#log-output", RichLog)

        log_output.clear()
        log_output.write(f"[bold]Loading logs for {log_source}...[/bold]\n")

        try:
            if log_source == "traefik":
                traefik_manager = get_traefik_manager()
                logs = traefik_manager.get_traefik_logs(tail=lines)
            elif ":" in log_source:
                # Stack logs
                stack_name, vm_name = log_source.split(":")
                config_loader = get_config_loader()
                vms_config = config_loader.load_vms()
                vm = vms_config.get_vm_by_name(vm_name)

                if vm:
                    stack = get_stack(stack_name)
                    if stack:
                        logs = stack.get_logs(vm, tail=lines)
                    else:
                        logs = f"Stack '{stack_name}' not found"
                else:
                    logs = f"VM '{vm_name}' not found"
            else:
                logs = "Unknown log source"

            log_output.clear()
            log_output.write(logs or "No logs available")

        except Exception as e:
            log_output.clear()
            log_output.write(f"[red]Error loading logs: {e}[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "refresh":
            self.action_refresh_logs()
        elif event.button.id == "clear":
            log_output = self.query_one("#log-output", RichLog)
            log_output.clear()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes."""
        if event.select.id == "log-source":
            self.action_refresh_logs()
