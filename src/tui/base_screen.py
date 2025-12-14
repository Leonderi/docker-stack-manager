"""Base screen class with common functionality."""

from textual.screen import Screen
from textual.widgets import Static


class BaseScreen(Screen):
    """Base screen with common methods for all TUI screens."""

    def show_status(self, message: str, level: str = "info") -> None:
        """Show a status message.

        Args:
            message: The message to display
            level: One of "info", "error", "success", "warning"
        """
        try:
            status = self.query_one("#status-message", Static)
            # Escape brackets to prevent Rich markup interpretation
            safe_message = message.replace("[", "\\[").replace("]", "\\]")
            if level == "error":
                status.update(f"[red]{safe_message}[/red]")
            elif level == "success":
                status.update(f"[green]{safe_message}[/green]")
            elif level == "warning":
                status.update(f"[yellow]{safe_message}[/yellow]")
            else:
                status.update(safe_message)
        except Exception:
            # Fallback to notify if status widget not found
            self.notify(message, severity="error" if level == "error" else "information")

    def show_error(self, message: str) -> None:
        """Show an error message."""
        self.show_status(message, "error")

    def show_success(self, message: str) -> None:
        """Show a success message."""
        self.show_status(message, "success")

    def show_warning(self, message: str) -> None:
        """Show a warning message."""
        self.show_status(message, "warning")

    def clear_status(self) -> None:
        """Clear the status message."""
        try:
            status = self.query_one("#status-message", Static)
            status.update("")
        except Exception:
            pass
