"""SSH key generation and management."""

from pathlib import Path
from typing import Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


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
        # Set directory permissions to 700
        self.keys_dir.chmod(0o700)

    def generate_keypair(self, name: str, comment: str = "") -> Tuple[Path, Path, str]:
        """
        Generate a new Ed25519 SSH keypair.

        Args:
            name: Base name for the key files (e.g., "vm-worker-1")
            comment: Optional comment for the public key

        Returns:
            Tuple of (private_key_path, public_key_path, public_key_content)
        """
        # Generate Ed25519 key
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        # Serialize private key (PEM format, no password)
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Serialize public key (OpenSSH format)
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH
        )

        # Add comment to public key if provided
        public_key_str = public_bytes.decode('utf-8')
        if comment:
            public_key_str = f"{public_key_str} {comment}"

        # Define file paths
        private_key_path = self.keys_dir / name
        public_key_path = self.keys_dir / f"{name}.pub"

        # Write private key
        private_key_path.write_bytes(private_bytes)
        private_key_path.chmod(0o600)  # Secure permissions

        # Write public key
        public_key_path.write_text(public_key_str + "\n")
        public_key_path.chmod(0o644)

        return private_key_path, public_key_path, public_key_str

    def get_keypair(self, name: str) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Get existing keypair paths.

        Returns:
            Tuple of (private_key_path, public_key_path) or (None, None) if not found
        """
        private_key_path = self.keys_dir / name
        public_key_path = self.keys_dir / f"{name}.pub"

        if private_key_path.exists() and public_key_path.exists():
            return private_key_path, public_key_path
        return None, None

    def get_or_create_keypair(self, name: str, comment: str = "") -> Tuple[Path, Path, str]:
        """
        Get existing keypair or create new one.

        Returns:
            Tuple of (private_key_path, public_key_path, public_key_content)
        """
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


# Global instance
_ssh_key_manager: Optional[SSHKeyManager] = None


def get_ssh_key_manager(keys_dir: Optional[Path] = None) -> SSHKeyManager:
    """Get or create the global SSH key manager instance."""
    global _ssh_key_manager
    if _ssh_key_manager is None or keys_dir is not None:
        _ssh_key_manager = SSHKeyManager(keys_dir)
    return _ssh_key_manager
