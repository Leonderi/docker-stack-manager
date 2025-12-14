"""First-run setup wizard screen."""

import ipaddress

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Input,
    Label,
    ProgressBar,
    Rule,
    Static,
)
from textual.message import Message


class SubnetIP(Horizontal):
    """Custom widget showing prefix + editable host input for IP addresses."""

    DEFAULT_CSS = """
    SubnetIP {
        width: 100%;
        height: 3;
        background: $boost;
        border: tall $background;
        padding: 0 1;
    }

    SubnetIP:focus-within {
        border: tall $accent;
    }

    SubnetIP .prefix {
        width: auto;
        height: 1;
        padding: 0;
        color: $text-muted;
        content-align: left middle;
    }

    SubnetIP .host-input {
        width: 1fr;
        height: 1;
        border: none;
        padding: 0;
        background: transparent;
    }

    SubnetIP .host-input:focus {
        border: none;
    }
    """

    class HostChanged(Message):
        """Message sent when the host part of the IP changes."""

        def __init__(self, subnet_ip: "SubnetIP", value: str) -> None:
            self.subnet_ip = subnet_ip
            self.value = value
            super().__init__()

    def __init__(
        self,
        prefix: str = "192.168.1.",
        host: str = "1",
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._prefix = prefix
        self._host = host

    def compose(self) -> ComposeResult:
        yield Static(self._prefix, classes="prefix")
        yield Input(value=self._host, classes="host-input")

    @property
    def prefix(self) -> str:
        """Get the network prefix."""
        return self._prefix

    @prefix.setter
    def prefix(self, value: str) -> None:
        """Set the network prefix."""
        self._prefix = value
        try:
            self.query_one(".prefix", Static).update(value)
        except Exception:
            pass

    @property
    def host(self) -> str:
        """Get the host part."""
        try:
            return self.query_one(".host-input", Input).value
        except Exception:
            return self._host

    @host.setter
    def host(self, value: str) -> None:
        """Set the host part."""
        self._host = value
        try:
            self.query_one(".host-input", Input).value = value
        except Exception:
            pass

    @property
    def value(self) -> str:
        """Get the full IP address."""
        return f"{self._prefix}{self.host}"

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle changes to the host input."""
        event.stop()
        self._host = event.value
        self.post_message(self.HostChanged(self, self.value))

from ...core.config_loader import (
    get_config_loader,
    InfraNetworkConfig,
    OPNsenseConfig,
    Settings,
    SSLConfig,
    TraefikConfig,
    VMConfig,
    VMNetworkConfig,
)


class SetupWizardScreen(Screen):
    """Setup wizard for first-time configuration."""

    CSS = """
    SetupWizardScreen {
        layout: vertical;
    }

    #wizard-container {
        height: 1fr;
        width: 100%;
    }

    #wizard-title {
        text-align: center;
        text-style: bold;
        padding: 1;
        height: auto;
    }

    #progress {
        height: auto;
        margin: 0 2;
    }

    #step-indicator {
        text-align: center;
        padding: 1;
        height: auto;
    }

    #wizard-content {
        height: 1fr;
        min-height: 10;
        border: solid $primary;
        margin: 1 2;
        padding: 1;
        overflow-y: auto;
    }

    #wizard-content > Vertical {
        height: auto;
        width: 100%;
    }

    #subnet-row {
        height: auto;
        width: 100%;
    }

    #subnet-row > Vertical {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }

    #wizard-buttons {
        height: auto;
        padding: 1;
        align: center middle;
    }

    #wizard-buttons Button {
        margin: 0 1;
    }

    #status-message {
        height: auto;
        text-align: center;
        padding: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self):
        super().__init__()
        self.current_step = 0
        self.total_steps = 4
        # Store values between steps
        self.data = {
            "network_ip": "192.168.1.0",
            "prefix": "24",
            "net_prefix": "192.168.1.",  # Fixed prefix for IPs
            "gateway_host": "1",
            "dns1": "192.168.1.1",  # DNS is fully editable
            "dns2": "8.8.8.8",
            "domain": "",
            "email": "",
            "ssl_staging": True,
            "traefik_name": "traefik-frontend",
            "traefik_host": "10",
            "traefik_user": "root",
            "traefik_key": "~/.ssh/id_rsa",
            "traefik_dashboard": True,
            "traefik_subdomain": "traefik",
        }

    def _netmask_to_prefix(self, netmask: str) -> int:
        """Convert netmask (255.255.255.0) to prefix length (24)."""
        try:
            parts = [int(p) for p in netmask.split('.')]
            if len(parts) != 4:
                return 0
            binary = ''.join(format(p, '08b') for p in parts)
            return binary.count('1')
        except (ValueError, AttributeError):
            return 0

    def _prefix_to_netmask(self, prefix: int) -> str:
        """Convert prefix length (24) to netmask (255.255.255.0)."""
        try:
            mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
            return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"
        except (ValueError, TypeError):
            return "255.255.255.0"

    def _get_network_prefix_string(self, network_ip: str, prefix: int) -> str:
        """Get the fixed network prefix string based on subnet."""
        try:
            octets = network_ip.split('.')
            if len(octets) != 4:
                return "192.168.1."

            # Determine fixed octets based on prefix
            if prefix >= 24:
                return f"{octets[0]}.{octets[1]}.{octets[2]}."
            elif prefix >= 16:
                return f"{octets[0]}.{octets[1]}."
            elif prefix >= 8:
                return f"{octets[0]}."
            else:
                return ""
        except (ValueError, IndexError):
            return "192.168.1."

    def _get_default_host_parts(self, prefix: int) -> dict[str, str]:
        """Get default host parts based on prefix length."""
        if prefix >= 24:
            return {"gateway": "1", "traefik": "10"}
        elif prefix >= 16:
            return {"gateway": "0.1", "traefik": "0.10"}
        elif prefix >= 8:
            return {"gateway": "0.0.1", "traefik": "0.0.10"}
        else:
            return {"gateway": "1", "traefik": "10"}

    def _is_ip_in_subnet(self, ip_str: str, network_ip: str, prefix: int) -> bool:
        """Check if an IP address is within the configured subnet."""
        try:
            network = ipaddress.ip_network(f"{network_ip}/{prefix}", strict=False)
            ip = ipaddress.ip_address(ip_str)
            return ip in network
        except (ValueError, TypeError):
            return False

    def _update_derived_ips(self) -> None:
        """Update gateway, DNS and traefik IP based on current network settings."""
        network_ip = self.data.get("network_ip", "")
        prefix_str = self.data.get("prefix", "24")

        try:
            prefix = int(prefix_str)
            if prefix < 8 or prefix > 30:
                return  # Invalid prefix, don't update
        except ValueError:
            return

        # Calculate new prefix and defaults
        net_prefix = self._get_network_prefix_string(network_ip, prefix)
        defaults = self._get_default_host_parts(prefix)

        # Update stored data
        self.data["net_prefix"] = net_prefix
        self.data["gateway_host"] = defaults["gateway"]
        self.data["traefik_host"] = defaults["traefik"]
        # Update DNS1 to full IP (gateway by default)
        self.data["dns1"] = f"{net_prefix}{defaults['gateway']}"

        # Update UI fields if they exist
        try:
            gateway_widget = self.query_one("#setup-gateway", SubnetIP)
            gateway_widget.prefix = net_prefix
            gateway_widget.host = defaults["gateway"]
        except Exception:
            pass
        try:
            self.query_one("#setup-dns1", Input).value = self.data["dns1"]
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes for auto-fill functionality."""
        input_id = event.input.id

        if input_id == "setup-network-ip":
            self.data["network_ip"] = event.value.strip()
            self._update_derived_ips()

        elif input_id == "setup-prefix":
            self.data["prefix"] = event.value.strip()
            # Update netmask display
            try:
                prefix = int(event.value.strip())
                if 0 <= prefix <= 32:
                    netmask = self._prefix_to_netmask(prefix)
                    self.query_one("#setup-netmask", Input).value = netmask
            except (ValueError, Exception):
                pass
            self._update_derived_ips()

        elif input_id == "setup-netmask":
            prefix = self._netmask_to_prefix(event.value.strip())
            if prefix > 0:
                self.data["prefix"] = str(prefix)
                try:
                    self.query_one("#setup-prefix", Input).value = str(prefix)
                except Exception:
                    pass
                self._update_derived_ips()

    def on_subnet_ip_host_changed(self, event: SubnetIP.HostChanged) -> None:
        """Handle changes to SubnetIP widgets."""
        widget_id = event.subnet_ip.id

        if widget_id == "setup-gateway":
            # Update DNS1 to match gateway (user can still change it)
            try:
                dns1_input = self.query_one("#setup-dns1", Input)
                # Only auto-update if DNS1 matches the old gateway or is empty
                old_gateway = f"{self.data.get('net_prefix', '')}{self.data.get('gateway_host', '')}"
                if dns1_input.value == old_gateway or not dns1_input.value.strip():
                    dns1_input.value = event.value
                    self.data["dns1"] = event.value
            except Exception:
                pass
            self.data["gateway_host"] = event.subnet_ip.host

    def compose(self) -> ComposeResult:
        """Compose the setup wizard screen."""
        scroll = VerticalScroll(id="wizard-content")
        scroll.can_focus = True
        yield Vertical(
            Static("[bold]Docker Stack Manager - Setup Wizard[/bold]", id="wizard-title"),
            ProgressBar(total=self.total_steps, id="progress"),
            Static("Step 1 of 4: Network Configuration", id="step-indicator"),
            scroll,
            Static("", id="status-message"),
            Horizontal(
                Button("Back", id="btn-back", variant="default", disabled=True),
                Button("Next", id="btn-next", variant="primary"),
                Button("Skip Setup", id="btn-skip", variant="warning"),
                id="wizard-buttons",
            ),
            id="wizard-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the wizard."""
        self.show_step(0)

    def save_current_step_data(self) -> None:
        """Save data from current step before switching."""
        try:
            if self.current_step == 0:
                self.data["network_ip"] = self.query_one("#setup-network-ip", Input).value
                self.data["prefix"] = self.query_one("#setup-prefix", Input).value
                gateway_widget = self.query_one("#setup-gateway", SubnetIP)
                self.data["gateway_host"] = gateway_widget.host
                self.data["dns1"] = self.query_one("#setup-dns1", Input).value
                self.data["dns2"] = self.query_one("#setup-dns2", Input).value
            elif self.current_step == 1:
                self.data["domain"] = self.query_one("#setup-domain", Input).value
                self.data["email"] = self.query_one("#setup-email", Input).value
                self.data["ssl_staging"] = self.query_one("#setup-ssl-staging", Checkbox).value
            elif self.current_step == 2:
                self.data["traefik_name"] = self.query_one("#setup-traefik-name", Input).value
                traefik_widget = self.query_one("#setup-traefik-ip", SubnetIP)
                self.data["traefik_host"] = traefik_widget.host
                self.data["traefik_user"] = self.query_one("#setup-traefik-user", Input).value
                self.data["traefik_key"] = self.query_one("#setup-traefik-key", Input).value
                self.data["traefik_dashboard"] = self.query_one("#setup-traefik-dashboard", Checkbox).value
                self.data["traefik_subdomain"] = self.query_one("#setup-traefik-subdomain", Input).value
        except Exception:
            pass

    def show_step(self, step: int) -> None:
        """Show a specific wizard step."""
        self.current_step = step
        content = self.query_one("#wizard-content", VerticalScroll)
        content.remove_children()

        # Update progress
        progress = self.query_one("#progress", ProgressBar)
        progress.progress = step

        # Update step indicator
        indicator = self.query_one("#step-indicator", Static)

        # Update buttons
        btn_back = self.query_one("#btn-back", Button)
        btn_next = self.query_one("#btn-next", Button)
        btn_back.disabled = step == 0

        if step == 0:
            indicator.update("Step 1 of 4: Network Configuration")
            btn_next.label = "Next"
            self._show_network_step(content)
        elif step == 1:
            indicator.update("Step 2 of 4: Domain & SSL")
            btn_next.label = "Next"
            self._show_domain_step(content)
        elif step == 2:
            indicator.update("Step 3 of 4: Traefik VM")
            btn_next.label = "Next"
            self._show_traefik_vm_step(content)
        elif step == 3:
            indicator.update("Step 4 of 4: Review & Finish")
            btn_next.label = "Finish Setup"
            self._show_review_step(content)

    def _show_network_step(self, container: VerticalScroll) -> None:
        """Show network configuration step."""
        # Calculate current netmask from prefix
        try:
            prefix = int(self.data["prefix"])
            netmask = self._prefix_to_netmask(prefix)
        except ValueError:
            netmask = "255.255.255.0"

        net_prefix = self.data.get("net_prefix", "192.168.1.")

        container.mount(
            Vertical(
                Static("[bold]Configure your infrastructure network[/bold]"),
                Static("This defines the network where your VMs are located."),
                Static("[dim]Gateway is locked to subnet. DNS can be external.[/dim]"),
                Rule(),
                Label("Network Address:"),
                Input(placeholder="192.168.1.0", id="setup-network-ip", value=self.data["network_ip"]),
                Horizontal(
                    Vertical(
                        Label("Prefix (CIDR):"),
                        Input(placeholder="24", id="setup-prefix", value=self.data["prefix"]),
                    ),
                    Vertical(
                        Label("Netmask:"),
                        Input(placeholder="255.255.255.0", id="setup-netmask", value=netmask),
                    ),
                    id="subnet-row",
                ),
                Rule(),
                Label("Gateway IP:"),
                SubnetIP(prefix=net_prefix, host=self.data["gateway_host"], id="setup-gateway"),
                Label("Primary DNS:"),
                Input(placeholder="192.168.1.1", id="setup-dns1", value=self.data["dns1"]),
                Label("Secondary DNS:"),
                Input(placeholder="8.8.8.8", id="setup-dns2", value=self.data["dns2"]),
            )
        )

    def _show_domain_step(self, container: VerticalScroll) -> None:
        """Show domain configuration step."""
        container.mount(
            Vertical(
                Static("[bold]Configure your domain[/bold]"),
                Static("This is the domain where your services will be accessible."),
                Rule(),
                Label("Domain Name:"),
                Input(placeholder="example.com", id="setup-domain", value=self.data["domain"]),
                Label("Admin Email (for SSL certificates):"),
                Input(placeholder="admin@example.com", id="setup-email", value=self.data["email"]),
                Rule(),
                Checkbox("Use Let's Encrypt Staging (for testing)", id="setup-ssl-staging", value=self.data["ssl_staging"]),
                Static("[dim]Use staging for testing to avoid rate limits[/dim]"),
            )
        )

    def _show_traefik_vm_step(self, container: VerticalScroll) -> None:
        """Show Traefik VM configuration step."""
        net_prefix = self.data.get("net_prefix", "192.168.1.")
        container.mount(
            Vertical(
                Static("[bold]Configure Traefik Frontend VM[/bold]"),
                Static("This VM will run Traefik and handle all incoming traffic."),
                Static("[dim]IP is locked to the configured subnet.[/dim]"),
                Rule(),
                Label("VM Name:"),
                Input(placeholder="traefik-frontend", id="setup-traefik-name", value=self.data["traefik_name"]),
                Label("IP Address:"),
                SubnetIP(prefix=net_prefix, host=self.data["traefik_host"], id="setup-traefik-ip"),
                Label("SSH User:"),
                Input(placeholder="root", id="setup-traefik-user", value=self.data["traefik_user"]),
                Label("SSH Key Path:"),
                Input(placeholder="~/.ssh/id_rsa", id="setup-traefik-key", value=self.data["traefik_key"]),
                Rule(),
                Static("[bold]Traefik Dashboard[/bold]"),
                Checkbox("Enable Dashboard", id="setup-traefik-dashboard", value=self.data["traefik_dashboard"]),
                Label("Dashboard Subdomain:"),
                Input(placeholder="traefik", id="setup-traefik-subdomain", value=self.data["traefik_subdomain"]),
            )
        )

    def _show_review_step(self, container: VerticalScroll) -> None:
        """Show review step with summary."""
        d = self.data
        subnet = f"{d['network_ip']}/{d['prefix']}"
        net_prefix = d.get("net_prefix", "")
        gateway = f"{net_prefix}{d['gateway_host']}"
        traefik_ip = f"{net_prefix}{d['traefik_host']}"
        container.mount(
            Vertical(
                Static("[bold]Review your configuration[/bold]"),
                Rule(),
                Static("[bold]Network:[/bold]"),
                Static(f"  Subnet: {subnet}"),
                Static(f"  Gateway: {gateway}"),
                Static(f"  DNS: {d['dns1']}, {d['dns2']}"),
                Rule(),
                Static("[bold]Domain:[/bold]"),
                Static(f"  Domain: {d['domain']}"),
                Static(f"  Email: {d['email']}"),
                Static(f"  SSL Staging: {'Yes' if d['ssl_staging'] else 'No'}"),
                Rule(),
                Static("[bold]Traefik VM:[/bold]"),
                Static(f"  Name: {d['traefik_name']}"),
                Static(f"  IP: {traefik_ip}"),
                Static(f"  User: {d['traefik_user']}"),
                Rule(),
                Static("[green]Click 'Finish Setup' to save configuration.[/green]"),
            )
        )

    def show_status(self, message: str, level: str = "info") -> None:
        """Show a status message."""
        status = self.query_one("#status-message", Static)
        if level == "error":
            status.update(f"[red]{message}[/red]")
        elif level == "success":
            status.update(f"[green]{message}[/green]")
        else:
            status.update(message)

    def validate_current_step(self) -> tuple[bool, str]:
        """Validate current step inputs."""
        try:
            if self.current_step == 0:
                network_ip = self.query_one("#setup-network-ip", Input).value.strip()
                prefix = self.query_one("#setup-prefix", Input).value.strip()
                gateway_widget = self.query_one("#setup-gateway", SubnetIP)
                gateway = gateway_widget.value
                if not network_ip:
                    return False, "Network address is required"
                if not prefix:
                    return False, "Prefix is required"
                if not gateway_widget.host.strip():
                    return False, "Gateway host part is required"
                # Validate format
                try:
                    prefix_int = int(prefix)
                    if prefix_int < 8 or prefix_int > 30:
                        return False, "Prefix must be between 8 and 30"
                    subnet = f"{network_ip}/{prefix}"
                    InfraNetworkConfig(subnet=subnet, gateway=gateway)
                except ValueError:
                    return False, "Invalid prefix format"
                except Exception as e:
                    return False, str(e)

            elif self.current_step == 1:
                domain = self.query_one("#setup-domain", Input).value.strip()
                email = self.query_one("#setup-email", Input).value.strip()
                if not domain:
                    return False, "Domain is required"
                if not email:
                    return False, "Email is required"
                if "@" not in email:
                    return False, "Invalid email format"

            elif self.current_step == 2:
                name = self.query_one("#setup-traefik-name", Input).value.strip()
                traefik_widget = self.query_one("#setup-traefik-ip", SubnetIP)
                if not name:
                    return False, "VM name is required"
                if not traefik_widget.host.strip():
                    return False, "IP host part is required"

            return True, ""

        except Exception as e:
            return False, str(e)

    def save_configuration(self) -> bool:
        """Save all configuration."""
        try:
            config_loader = get_config_loader()
            d = self.data

            # Build subnet from network_ip and prefix
            subnet = f"{d['network_ip'].strip()}/{d['prefix'].strip()}"
            net_prefix = d.get("net_prefix", "")

            # Combine prefix + host for locked IPs
            gateway = f"{net_prefix}{d['gateway_host'].strip()}"
            traefik_ip = f"{net_prefix}{d['traefik_host'].strip()}"

            # Build settings
            settings = Settings(
                domain=d["domain"].strip(),
                email=d["email"].strip(),
                ssl=SSLConfig(
                    provider="letsencrypt",
                    staging=d["ssl_staging"],
                ),
                network=InfraNetworkConfig(
                    subnet=subnet,
                    gateway=gateway,
                    dns_primary=d["dns1"].strip(),
                    dns_secondary=d["dns2"].strip(),
                ),
                traefik=TraefikConfig(
                    dashboard_enabled=d["traefik_dashboard"],
                    dashboard_subdomain=d["traefik_subdomain"].strip(),
                ),
                opnsense=OPNsenseConfig(),
                first_run_complete=True,
            )

            config_loader.save_settings(settings)

            # Create Traefik VM
            traefik_vm = VMConfig(
                name=d["traefik_name"].strip(),
                host=traefik_ip,
                user=d["traefik_user"].strip(),
                ssh_key=d["traefik_key"].strip(),
                role="traefik",
                description="Traefik Reverse Proxy",
                network=VMNetworkConfig(
                    ip_address=traefik_ip,
                    gateway=settings.network.gateway,
                    dns_primary=settings.network.dns_primary,
                    dns_secondary=settings.network.dns_secondary,
                ),
            )

            config_loader.add_vm(traefik_vm)

            return True

        except Exception as e:
            self.show_status(f"Error saving configuration: {e}", "error")
            return False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-next":
            # Validate current step
            valid, error = self.validate_current_step()
            if not valid:
                self.show_status(error, "error")
                return

            # Save current step data before moving
            self.save_current_step_data()

            if self.current_step < self.total_steps - 1:
                self.show_step(self.current_step + 1)
            else:
                # Finish setup
                if self.save_configuration():
                    self.notify("Setup complete!")
                    self.app.pop_screen()
                    self.app.push_screen("dashboard")

        elif button_id == "btn-back":
            # Save current step data before going back
            self.save_current_step_data()
            if self.current_step > 0:
                self.show_step(self.current_step - 1)

        elif button_id == "btn-skip":
            # Skip setup and go to dashboard
            config_loader = get_config_loader()
            config_loader.complete_first_run()
            self.app.pop_screen()
            self.app.push_screen("dashboard")

    def action_cancel(self) -> None:
        """Cancel the wizard."""
        self.app.pop_screen()
