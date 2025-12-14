# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docker Stack Manager is a Python TUI application for deploying and managing Docker Compose stacks across multiple VMs with automatic Traefik reverse proxy configuration and Let's Encrypt SSL certificates.

## Commands

```bash
# Setup virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the application
python main.py
```

## Architecture

### Core Managers (`src/core/`)
- **SSHManager** (`ssh_manager.py`): Handles SSH connections to remote VMs using Fabric/Paramiko. Provides command execution, file upload/download, and connection pooling via global singleton.
- **DockerManager** (`docker_manager.py`): Manages Docker and Docker Compose operations on remote VMs through SSHManager. Handles container lifecycle, compose up/down, logs, and image management.
- **TraefikManager** (`traefik_manager.py`): Deploys and configures Traefik reverse proxy. Generates static/dynamic YAML configs, manages SSL certificates via Let's Encrypt, and handles service routing.
- **ConfigLoader** (`config_loader.py`): Loads/saves YAML configuration from `config/` directory. Uses Pydantic models for Settings (domain, SSL, network) and VMsConfig (VM definitions).

### Stack System (`src/stacks/`)
- **BaseStack** (`base.py`): Abstract base class all stacks inherit from. Handles deployment workflow: validate config → create directory → upload compose file → pull images → start containers → add Traefik route.
- **Stack Registry**: Stacks register via `@register_stack` decorator. Access with `get_available_stacks()` and `get_stack(name)`.
- **Stack Definitions** (`definitions/`): Individual stack implementations (Grafana, InfluxDB, Vaultwarden, N8N, Paperless, etc.). Each defines `info` property and `generate_compose()` method.

### TUI (`src/tui/`)
- Built with Textual framework
- **DockerStackManager** (`app.py`): Main app class with screen navigation and key bindings
- **Screens** (`screens/`): Dashboard, VM Manager, Stack Deploy, Logs, Settings, Setup Wizard

### Key Patterns
- Global singleton instances accessed via `get_*()` functions (e.g., `get_ssh_manager()`, `get_docker_manager()`)
- All remote operations go through SSHManager → DockerManager → TraefikManager chain
- Stacks deployed to `/opt/stacks/{stack_name}/` on remote VMs
- Traefik configs stored at `/opt/traefik/` with dynamic routes in `/opt/traefik/dynamic/`

### Configuration
- YAML configs stored in `config/` directory (created on first run)
- `settings.yaml`: Domain, email, SSL settings, network config
- `vms.yaml`: VM definitions with SSH connection details and roles (traefik/worker)

### Adding New Stacks
1. Create new file in `src/stacks/definitions/`
2. Inherit from `BaseStack`, decorate with `@register_stack`
3. Implement `info` property returning `StackInfo` and `generate_compose()` method
4. Import in `src/stacks/definitions/__init__.py`
