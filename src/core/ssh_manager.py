"""SSH connection and key management."""

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fabric import Connection
from invoke.exceptions import UnexpectedExit
from paramiko import RSAKey, Ed25519Key, ECDSAKey

from .config_loader import VMConfig


# =============================================================================
# SSH Key Management
# =============================================================================

class SSHKeyManager:
    """Manages SSH key generation and storage."""

    def __init__(self, keys_dir: Optional[Path] = None):
        """Initialize with keys directory."""
        if keys_dir is None:
            keys_dir = Path(__file__).parent.parent.parent / "config" / "ssh_keys"
        self.keys_dir = Path(keys_dir)
        self._ensure_keys_dir()

    def _ensure_keys_dir(self) -> None:
        """Ensure keys directory exists with proper permissions."""
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.keys_dir.chmod(0o700)

    def generate_keypair(self, name: str, comment: str = "") -> Tuple[Path, Path, str]:
        """Generate a new Ed25519 SSH keypair."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption()
        )

        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH
        )

        public_key_str = public_bytes.decode('utf-8')
        if comment:
            public_key_str = f"{public_key_str} {comment}"

        private_key_path = self.keys_dir / name
        public_key_path = self.keys_dir / f"{name}.pub"

        private_key_path.write_bytes(private_bytes)
        private_key_path.chmod(0o600)

        public_key_path.write_text(public_key_str + "\n")
        public_key_path.chmod(0o644)

        return private_key_path, public_key_path, public_key_str

    def get_keypair(self, name: str) -> Tuple[Optional[Path], Optional[Path]]:
        """Get existing keypair paths."""
        private_key_path = self.keys_dir / name
        public_key_path = self.keys_dir / f"{name}.pub"

        if private_key_path.exists() and public_key_path.exists():
            return private_key_path, public_key_path
        return None, None

    def get_or_create_keypair(self, name: str, comment: str = "") -> Tuple[Path, Path, str]:
        """Get existing keypair or create new one."""
        private_path, public_path = self.get_keypair(name)

        if private_path and public_path:
            public_key_content = public_path.read_text().strip()
            return private_path, public_path, public_key_content

        return self.generate_keypair(name, comment)

    def get_public_key(self, name: str) -> Optional[str]:
        """Get public key content by name."""
        public_key_path = self.keys_dir / f"{name}.pub"
        if public_key_path.exists():
            return public_key_path.read_text().strip()
        return None

    def delete_keypair(self, name: str) -> bool:
        """Delete a keypair by name."""
        private_key_path = self.keys_dir / name
        public_key_path = self.keys_dir / f"{name}.pub"

        deleted = False
        if private_key_path.exists():
            private_key_path.unlink()
            deleted = True
        if public_key_path.exists():
            public_key_path.unlink()
            deleted = True

        return deleted

    def list_keys(self) -> list[str]:
        """List all key names (without extensions)."""
        keys = set()
        for path in self.keys_dir.glob("*"):
            if path.suffix == ".pub":
                keys.add(path.stem)
            elif not path.suffix and path.is_file():
                keys.add(path.name)
        return sorted(keys)


# Global SSH key manager instance
_ssh_key_manager: Optional[SSHKeyManager] = None


def get_ssh_key_manager(keys_dir: Optional[Path] = None) -> SSHKeyManager:
    """Get or create the global SSH key manager instance."""
    global _ssh_key_manager
    if _ssh_key_manager is None or keys_dir is not None:
        _ssh_key_manager = SSHKeyManager(keys_dir)
    return _ssh_key_manager


# =============================================================================
# SSH Connection Management
# =============================================================================


@dataclass
class CommandResult:
    """Result of a remote command execution."""
    stdout: str
    stderr: str
    return_code: int
    success: bool

    @classmethod
    def from_fabric_result(cls, result) -> "CommandResult":
        """Create from Fabric result object."""
        return cls(
            stdout=result.stdout.strip() if result.stdout else "",
            stderr=result.stderr.strip() if result.stderr else "",
            return_code=result.return_code,
            success=result.return_code == 0
        )


class SSHManager:
    """Manages SSH connections to VMs."""

    def __init__(self):
        """Initialize SSH manager."""
        self._connections: dict[str, Connection] = {}

    def _load_key(self, key_path: Path):
        """Load SSH private key from file."""
        key_path = key_path.expanduser()
        if not key_path.exists():
            raise FileNotFoundError(f"SSH key not found: {key_path}")

        key_content = key_path.read_text()

        # Try different key types
        for key_class in [RSAKey, Ed25519Key, ECDSAKey]:
            try:
                return key_class.from_private_key(io.StringIO(key_content))
            except Exception:
                continue

        raise ValueError(f"Unable to load SSH key: {key_path}")

    def get_connection(self, vm: VMConfig) -> Connection:
        """Get or create a connection to a VM."""
        if vm.name not in self._connections:
            key = self._load_key(vm.ssh_key_path)
            self._connections[vm.name] = Connection(
                host=vm.host,
                user=vm.user,
                connect_kwargs={"pkey": key}
            )
        return self._connections[vm.name]

    def close_connection(self, vm_name: str) -> None:
        """Close a specific connection."""
        if vm_name in self._connections:
            try:
                self._connections[vm_name].close()
            except Exception:
                pass
            del self._connections[vm_name]

    def close_all(self) -> None:
        """Close all connections."""
        for name in list(self._connections.keys()):
            self.close_connection(name)

    def run_command(
        self,
        vm: VMConfig,
        command: str,
        hide: bool = True,
        warn: bool = True
    ) -> CommandResult:
        """Execute a command on a VM."""
        conn = self.get_connection(vm)
        result = conn.run(command, hide=hide, warn=warn)
        return CommandResult.from_fabric_result(result)

    def test_connection(self, vm: VMConfig) -> tuple[bool, str]:
        """Test SSH connection to a VM."""
        try:
            result = self.run_command(vm, "echo 'Connection successful'")
            if result.success:
                return True, "Connection successful"
            return False, result.stderr or "Unknown error"
        except Exception as e:
            return False, str(e)

    def upload_file(
        self,
        vm: VMConfig,
        local_path: Path,
        remote_path: str
    ) -> bool:
        """Upload a file to a VM."""
        try:
            conn = self.get_connection(vm)
            conn.put(str(local_path), remote_path)
            return True
        except Exception:
            return False

    def upload_content(
        self,
        vm: VMConfig,
        content: str,
        remote_path: str
    ) -> bool:
        """Upload string content as a file to a VM."""
        try:
            conn = self.get_connection(vm)
            conn.put(io.StringIO(content), remote_path)
            return True
        except Exception:
            return False

    def download_file(
        self,
        vm: VMConfig,
        remote_path: str,
        local_path: Path
    ) -> bool:
        """Download a file from a VM."""
        try:
            conn = self.get_connection(vm)
            conn.get(remote_path, str(local_path))
            return True
        except Exception:
            return False

    def file_exists(self, vm: VMConfig, path: str) -> bool:
        """Check if a file exists on the VM."""
        result = self.run_command(vm, f"test -f {path} && echo 'exists'")
        return result.stdout == "exists"

    def dir_exists(self, vm: VMConfig, path: str) -> bool:
        """Check if a directory exists on the VM."""
        result = self.run_command(vm, f"test -d {path} && echo 'exists'")
        return result.stdout == "exists"

    def mkdir(self, vm: VMConfig, path: str) -> bool:
        """Create a directory on the VM."""
        result = self.run_command(vm, f"mkdir -p {path}")
        return result.success


class VMInitializer:
    """Initialize VMs/LXCs with standard setup."""

    SETUP_SCRIPT = '''#!/bin/bash
set -e

echo "=== System Update ==="
apt update && DEBIAN_FRONTEND=noninteractive apt upgrade -y

echo "=== Installing Base Packages ==="
DEBIAN_FRONTEND=noninteractive apt install -y sudo curl wget git ca-certificates gnupg ufw

echo "=== Creating User 'manager' ==="
if ! id -u manager >/dev/null 2>&1; then
    useradd -m -s /bin/bash -G sudo manager
fi
echo "manager ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/manager
chmod 440 /etc/sudoers.d/manager

echo "=== Setting up SSH Key ==="
mkdir -p /home/manager/.ssh
echo "{public_key}" > /home/manager/.ssh/authorized_keys
chown -R manager:manager /home/manager/.ssh
chmod 700 /home/manager/.ssh
chmod 600 /home/manager/.ssh/authorized_keys

echo "=== Locking Root Account ==="
passwd -l root
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

echo "=== Configuring Firewall ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable

echo "=== Installing Docker ==="
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker manager

echo "=== Verifying Docker ==="
docker --version
docker compose version

echo "=== Setup Complete ==="
'''

    def __init__(self, ssh_manager: "SSHManager"):
        """Initialize with SSH manager."""
        self.ssh = ssh_manager
        self.key_manager = get_ssh_key_manager()

    def initialize_vm(
        self,
        host: str,
        root_key_path: Path,
        vm_name: str,
        callback: Optional[Callable[[str], None]] = None,
        port: int = 22,
    ) -> tuple[bool, Path, str]:
        """Initialize a VM with standard setup.

        Args:
            host: VM IP address
            root_key_path: Path to root's private SSH key
            vm_name: Name of the VM (for key naming)
            callback: Progress callback function
            port: SSH port

        Returns:
            Tuple of (success, manager_key_path, message)
        """
        def log(msg: str):
            if callback:
                callback(msg)

        try:
            # Generate manager keypair
            log("Generating SSH keypair for manager user...")

            key_name = f"{vm_name}_manager"
            private_path, public_path, public_key = self.key_manager.get_or_create_keypair(
                key_name, comment=f"manager@{vm_name}"
            )
            log(f"✓ Key generated: {key_name}")

            # Create temporary VMConfig for root connection
            root_vm = VMConfig(
                name=f"{vm_name}_root_temp",
                host=host,
                user="root",
                ssh_key=str(root_key_path),
                ssh_port=port,
            )

            # Connect as root
            log(f"Connecting to {host} as root...")

            try:
                conn = self.ssh.get_connection(root_vm)
                log("✓ Connected to VM")
            except Exception as e:
                return False, Path(), f"Failed to connect as root: {e}"

            # Run setup steps individually for better logging
            steps = [
                ("Updating system packages", "apt update && DEBIAN_FRONTEND=noninteractive apt upgrade -y"),
                ("Installing base packages", "DEBIAN_FRONTEND=noninteractive apt install -y sudo curl wget git ca-certificates gnupg ufw"),
                ("Creating 'manager' user", '''
                    if ! id -u manager >/dev/null 2>&1; then
                        useradd -m -s /bin/bash -G sudo manager
                    fi
                    echo "manager ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/manager
                    chmod 440 /etc/sudoers.d/manager
                '''),
                ("Setting up SSH key for manager", f'''
                    mkdir -p /home/manager/.ssh
                    echo "{public_key}" > /home/manager/.ssh/authorized_keys
                    chown -R manager:manager /home/manager/.ssh
                    chmod 700 /home/manager/.ssh
                    chmod 600 /home/manager/.ssh/authorized_keys
                '''),
                ("Securing SSH configuration", '''
                    passwd -l root
                    sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
                    sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
                    systemctl restart sshd
                '''),
                ("Configuring firewall", '''
                    ufw default deny incoming
                    ufw default allow outgoing
                    ufw allow 22/tcp comment 'SSH'
                    ufw allow 80/tcp comment 'HTTP'
                    ufw allow 443/tcp comment 'HTTPS'
                    ufw --force enable
                '''),
                ("Installing Docker", '''
                    if ! command -v docker &> /dev/null; then
                        curl -fsSL https://get.docker.com | sh
                    fi
                    usermod -aG docker manager
                '''),
                ("Verifying Docker installation", "docker --version && docker compose version"),
            ]

            for step_name, command in steps:
                log(f"→ {step_name}...")
                result = self.ssh.run_command(root_vm, command)
                if not result.success:
                    # Close root connection
                    self.ssh.close_connection(root_vm.name)
                    log(f"✗ {step_name} failed")
                    return False, private_path, f"{step_name} failed:\n{result.stderr}\n{result.stdout}"
                log(f"✓ {step_name}")

            # Close root connection
            self.ssh.close_connection(root_vm.name)

            # Test connection as manager
            log("Testing connection as manager...")

            manager_vm = VMConfig(
                name=f"{vm_name}_manager_test",
                host=host,
                user="manager",
                ssh_key=str(private_path),
                ssh_port=port,
            )

            test_ok, test_msg = self.ssh.test_connection(manager_vm)
            self.ssh.close_connection(manager_vm.name)

            if test_ok:
                log("✓ Manager login successful!")
                return True, private_path, "VM initialized successfully"
            else:
                return False, private_path, f"Setup completed but manager login failed: {test_msg}"

        except Exception as e:
            return False, Path(), f"Initialization failed: {e}"

    def run_setup_step(
        self,
        vm: VMConfig,
        step_name: str,
        command: str,
        callback: Optional[Callable[[str], None]] = None,
    ) -> tuple[bool, str]:
        """Run a single setup step on a VM.

        Args:
            vm: VM configuration
            step_name: Name of the step for logging
            command: Command to execute
            callback: Progress callback

        Returns:
            Tuple of (success, output)
        """
        if callback:
            callback(f"Running: {step_name}...")

        result = self.ssh.run_command(vm, command)

        if result.success:
            if callback:
                callback(f"✓ {step_name} completed")
            return True, result.stdout
        else:
            if callback:
                callback(f"✗ {step_name} failed: {result.stderr}")
            return False, result.stderr


# Global SSH manager instance
_ssh_manager: Optional[SSHManager] = None
_vm_initializer: Optional[VMInitializer] = None


def get_ssh_manager() -> SSHManager:
    """Get or create the global SSH manager instance."""
    global _ssh_manager
    if _ssh_manager is None:
        _ssh_manager = SSHManager()
    return _ssh_manager


def get_vm_initializer() -> VMInitializer:
    """Get or create the global VM initializer instance."""
    global _vm_initializer
    if _vm_initializer is None:
        _vm_initializer = VMInitializer(get_ssh_manager())
    return _vm_initializer
