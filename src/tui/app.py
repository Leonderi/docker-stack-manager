"""Main TUI application using Textual."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from .screens.dashboard import DashboardScreen
from .screens.vm_manager import VMManagerScreen
from .screens.stack_deploy import StackDeployScreen
from .screens.logs import LogViewerScreen
from .screens.settings import SettingsScreen
from .screens.lxc_create import LXCCreateScreen


class DockerStackManager(App):
    """Docker Stack Manager TUI Application."""

    TITLE = "Docker Stack Manager"
    SUB_TITLE = "Manage Docker stacks across VMs"

    CSS = """
    Screen {
        background: $surface;
    }

    #main-content {
        height: 100%;
        padding: 1;
    }

    .box {
        border: solid $primary;
        padding: 1;
        margin: 1;
    }

    .title {
        text-style: bold;
        color: $text;
        padding: 1;
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

    DataTable {
        height: auto;
        max-height: 20;
    }

    .status-running {
        color: $success;
    }

    .status-stopped {
        color: $error;
    }

    .status-unknown {
        color: $warning;
    }

    Button {
        margin: 1;
    }

    Input {
        margin: 1 0;
    }

    Label {
        margin: 1 0 0 0;
    }

    #sidebar {
        width: 30;
        dock: left;
        border-right: solid $primary;
        padding: 1;
    }

    #content {
        padding: 1;
    }

    ListView {
        height: auto;
        max-height: 15;
        border: solid $primary;
        margin: 1 0;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem:hover {
        background: $primary 20%;
    }

    ListItem.-selected {
        background: $primary 40%;
    }

    RichLog {
        height: 100%;
        border: solid $primary;
    }

    #log-container {
        height: 1fr;
        margin: 1;
    }

    Select {
        margin: 1 0;
    }

    .form-group {
        margin: 1 0;
    }

    #deploy-form {
        padding: 1;
        height: auto;
    }

    #env-vars {
        height: auto;
        max-height: 15;
    }

    ProgressBar {
        margin: 1 0;
    }

    TabbedContent {
        height: auto;
    }

    TabPane {
        padding: 1;
    }

    /* Default VerticalScroll for lists etc */
    VerticalScroll {
        height: auto;
        max-height: 25;
    }

    Rule {
        margin: 1 0;
    }

    Checkbox {
        margin: 1 0;
    }

    #action-buttons {
        margin: 1;
    }

    #ip-row {
        height: auto;
    }

    #ip-row Input {
        width: 1fr;
    }

    #ip-row Button {
        width: auto;
    }
    """

    BINDINGS = [
        Binding("d", "push_screen('dashboard')", "Dashboard", show=True),
        Binding("v", "push_screen('vms')", "VMs", show=True),
        Binding("s", "push_screen('stacks')", "Stacks", show=True),
        Binding("l", "push_screen('logs')", "Logs", show=True),
        Binding("c", "push_screen('settings')", "Settings", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("escape", "go_back", "Back", show=True),
    ]

    SCREENS = {
        "dashboard": DashboardScreen,
        "vms": VMManagerScreen,
        "stacks": StackDeployScreen,
        "logs": LogViewerScreen,
        "settings": SettingsScreen,
        "lxc_create": LXCCreateScreen,
    }

    def compose(self) -> ComposeResult:
        """Compose the main application."""
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.push_screen("dashboard")

    def action_go_back(self) -> None:
        """Go back to the previous screen."""
        if len(self.screen_stack) > 1:
            self.pop_screen()


def run_app():
    """Run the TUI application."""
    app = DockerStackManager()
    app.run()
