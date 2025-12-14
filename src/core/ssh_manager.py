"""SSH connection manager using Fabric."""

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fabric import Connection
from paramiko import RSAKey, Ed25519Key, ECDSAKey

from .config_loader import VMConfig


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


# Global SSH manager instance
_ssh_manager: Optional[SSHManager] = None


def get_ssh_manager() -> SSHManager:
    """Get or create the global SSH manager instance."""
    global _ssh_manager
    if _ssh_manager is None:
        _ssh_manager = SSHManager()
    return _ssh_manager
