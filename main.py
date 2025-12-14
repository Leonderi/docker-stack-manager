#!/usr/bin/env python3
"""Docker Stack Manager - Main entry point."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    """Main entry point."""
    # Import stacks to register them
    from src.stacks import definitions  # noqa: F401

    # Run the TUI
    from src.tui import run_app
    run_app()


if __name__ == "__main__":
    main()
