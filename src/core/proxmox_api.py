"""Proxmox VE API client for LXC container management."""

import time
import urllib3
from typing import Any, Optional

import requests

# Disable SSL warnings for self-signed certificates (common in Proxmox)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ProxmoxAPIError(Exception):
    """Exception raised for Proxmox API errors."""

    def __init__(self, message: str, status_code: int = 0, response: dict = None):
        self.message = message
        self.status_code = status_code
        self.response = response or {}
        super().__init__(self.message)


class ProxmoxAPI:
    """Client for Proxmox VE REST API."""

    def __init__(
        self,
        host: str,
        user: str,
        token_name: str,
        token_value: str,
        port: int = 8006,
        verify_ssl: bool = False,
    ):
        """
        Initialize Proxmox API client.

        Args:
            host: Proxmox host IP or hostname
            user: Username (e.g., "root@pam")
            token_name: API token name
            token_value: API token value (UUID)
            port: API port (default 8006)
            verify_ssl: Whether to verify SSL certificates
        """
        self.host = host
        self.port = port
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{host}:{port}/api2/json"

        # Build authorization header
        self.auth_header = f"PVEAPIToken={user}!{token_name}={token_value}"
        self.headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict = None,
        params: dict = None,
    ) -> dict:
        """Make an API request."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            # For POST requests, use form data instead of JSON (Proxmox prefers this)
            if method in ("POST", "PUT") and data:
                response = requests.request(
                    method=method,
                    url=url,
                    headers={"Authorization": self.auth_header},
                    data=data,
                    verify=self.verify_ssl,
                    timeout=30,
                )
            else:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    verify=self.verify_ssl,
                    timeout=30,
                )

            # Parse response - handle empty responses
            response_text = response.text.strip()
            if not response_text:
                # Empty response is OK for some operations (start/stop return UPID in data)
                result = {"data": None}
            else:
                try:
                    result = response.json()
                except ValueError:
                    # If response isn't JSON but not empty, wrap it
                    result = {"data": response_text}

            # Check for errors
            if response.status_code >= 400:
                error_msg = result.get("errors", result.get("message", str(result)))
                raise ProxmoxAPIError(
                    f"API error: {error_msg}",
                    status_code=response.status_code,
                    response=result,
                )

            return result.get("data", result)

        except requests.exceptions.RequestException as e:
            raise ProxmoxAPIError(f"Connection error: {e}")

    def get(self, endpoint: str, params: dict = None) -> Any:
        """GET request."""
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: dict = None) -> Any:
        """POST request."""
        return self._request("POST", endpoint, data=data)

    def put(self, endpoint: str, data: dict = None) -> Any:
        """PUT request."""
        return self._request("PUT", endpoint, data=data)

    def delete(self, endpoint: str) -> Any:
        """DELETE request."""
        return self._request("DELETE", endpoint)

    # ==================== Cluster/Node Methods ====================

    def get_nodes(self) -> list[dict]:
        """Get all nodes in the cluster."""
        return self.get("nodes")

    def get_node_status(self, node: str) -> dict:
        """Get status of a specific node."""
        return self.get(f"nodes/{node}/status")

    def get_version(self) -> dict:
        """Get Proxmox version info."""
        return self.get("version")

    def test_connection(self) -> tuple[bool, str]:
        """Test API connection."""
        try:
            version = self.get_version()
            return True, f"Connected to Proxmox VE {version.get('version', 'unknown')}"
        except ProxmoxAPIError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Connection failed: {e}"

    # ==================== LXC Container Methods ====================

    def get_lxc_containers(self, node: str) -> list[dict]:
        """Get all LXC containers on a node."""
        return self.get(f"nodes/{node}/lxc")

    def get_lxc_config(self, node: str, vmid: int) -> dict:
        """Get LXC container configuration."""
        return self.get(f"nodes/{node}/lxc/{vmid}/config")

    def get_lxc_status(self, node: str, vmid: int) -> dict:
        """Get LXC container status."""
        return self.get(f"nodes/{node}/lxc/{vmid}/status/current")

    def get_next_vmid(self) -> int:
        """Get the next available VMID."""
        return int(self.get("cluster/nextid"))

    def is_vmid_available(self, vmid: int) -> bool:
        """Check if a VMID is available (not in use)."""
        try:
            resources = self.get("cluster/resources", params={"type": "vm"})
            used_vmids = {r.get("vmid") for r in resources}
            return vmid not in used_vmids
        except ProxmoxAPIError:
            return False

    def get_storage_list(self, node: str) -> list[dict]:
        """Get available storage on a node."""
        return self.get(f"nodes/{node}/storage")

    def get_lxc_templates(self, node: str, storage: str) -> list[dict]:
        """Get available LXC templates on a storage."""
        content = self.get(f"nodes/{node}/storage/{storage}/content")
        return [item for item in content if item.get("content") == "vztmpl"]

    def download_lxc_template(
        self,
        node: str,
        storage: str,
        template: str,
    ) -> str:
        """
        Download an LXC template from the repository.

        Args:
            node: Node name
            storage: Storage ID
            template: Template name (e.g., "debian-12-standard_12.2-1_amd64.tar.zst")

        Returns:
            Task ID (UPID)
        """
        data = {
            "storage": storage,
            "template": template,
        }
        return self.post(f"nodes/{node}/aplinfo", data=data)

    def create_lxc(
        self,
        node: str,
        vmid: int,
        hostname: str,
        ostemplate: str,
        storage: str = "local-lvm",
        rootfs_size: int = 8,
        memory: int = 512,
        swap: int = 512,
        cores: int = 1,
        password: str = None,
        ssh_public_keys: str = None,
        net0: str = None,
        nameserver: str = None,
        searchdomain: str = None,
        start_after_create: bool = True,
        unprivileged: bool = True,
        features: str = None,
        onboot: bool = True,
        description: str = "",
    ) -> str:
        """
        Create a new LXC container.

        Args:
            node: Target node
            vmid: VM ID
            hostname: Container hostname
            ostemplate: Template path (e.g., "local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst")
            storage: Storage for rootfs
            rootfs_size: Root filesystem size in GB
            memory: Memory in MB
            swap: Swap in MB
            cores: Number of CPU cores
            password: Root password (optional if ssh_public_keys provided)
            ssh_public_keys: SSH public keys for root user
            net0: Network config (e.g., "name=eth0,bridge=vmbr0,ip=192.168.1.100/24,gw=192.168.1.1")
            nameserver: DNS servers
            searchdomain: Search domain
            start_after_create: Start container after creation
            unprivileged: Create unprivileged container
            features: Feature flags (e.g., "nesting=1")
            onboot: Start on boot
            description: Container description

        Returns:
            Task ID (UPID)
        """
        data = {
            "vmid": vmid,
            "hostname": hostname,
            "ostemplate": ostemplate,
            "storage": storage,
            "rootfs": f"{storage}:{rootfs_size}",
            "memory": memory,
            "swap": swap,
            "cores": cores,
            "unprivileged": 1 if unprivileged else 0,
            "onboot": 1 if onboot else 0,
            "start": 1 if start_after_create else 0,
        }

        if password:
            data["password"] = password
        if ssh_public_keys:
            data["ssh-public-keys"] = ssh_public_keys
        if net0:
            data["net0"] = net0
        if nameserver:
            data["nameserver"] = nameserver
        if searchdomain:
            data["searchdomain"] = searchdomain
        if features:
            data["features"] = features
        if description:
            data["description"] = description

        return self.post(f"nodes/{node}/lxc", data=data)

    def start_lxc(self, node: str, vmid: int) -> str:
        """Start an LXC container."""
        return self.post(f"nodes/{node}/lxc/{vmid}/status/start")

    def stop_lxc(self, node: str, vmid: int) -> str:
        """Stop an LXC container."""
        return self.post(f"nodes/{node}/lxc/{vmid}/status/stop")

    def shutdown_lxc(self, node: str, vmid: int, timeout: int = 60) -> str:
        """Gracefully shutdown an LXC container."""
        return self.post(f"nodes/{node}/lxc/{vmid}/status/shutdown", {"timeout": timeout})

    def delete_lxc(self, node: str, vmid: int, purge: bool = True) -> str:
        """Delete an LXC container."""
        params = {"purge": 1} if purge else {}
        return self.delete(f"nodes/{node}/lxc/{vmid}")

    def clone_lxc(
        self,
        node: str,
        vmid: int,
        newid: int,
        hostname: str = None,
        target: str = None,
        full: bool = True,
    ) -> str:
        """Clone an LXC container."""
        data = {
            "newid": newid,
            "full": 1 if full else 0,
        }
        if hostname:
            data["hostname"] = hostname
        if target:
            data["target"] = target

        return self.post(f"nodes/{node}/lxc/{vmid}/clone", data=data)

    # ==================== QEMU VM Methods ====================

    def get_qemu_vms(self, node: str) -> list[dict]:
        """Get all QEMU VMs on a node."""
        return self.get(f"nodes/{node}/qemu")

    def get_qemu_status(self, node: str, vmid: int) -> dict:
        """Get QEMU VM status."""
        return self.get(f"nodes/{node}/qemu/{vmid}/status/current")

    def start_qemu(self, node: str, vmid: int) -> str:
        """Start a QEMU VM."""
        return self.post(f"nodes/{node}/qemu/{vmid}/status/start")

    def stop_qemu(self, node: str, vmid: int) -> str:
        """Stop a QEMU VM."""
        return self.post(f"nodes/{node}/qemu/{vmid}/status/stop")

    def shutdown_qemu(self, node: str, vmid: int, timeout: int = 60) -> str:
        """Gracefully shutdown a QEMU VM."""
        return self.post(f"nodes/{node}/qemu/{vmid}/status/shutdown", {"timeout": timeout})

    # ==================== Generic VM Methods ====================

    def start_vm(self, node: str, vmid: int, vm_type: str = "lxc") -> str:
        """Start a VM/LXC container."""
        if vm_type == "lxc":
            return self.start_lxc(node, vmid)
        elif vm_type == "qemu":
            return self.start_qemu(node, vmid)
        else:
            raise ProxmoxAPIError(f"Unknown VM type: {vm_type}")

    def stop_vm(self, node: str, vmid: int, vm_type: str = "lxc") -> str:
        """Stop a VM/LXC container."""
        if vm_type == "lxc":
            return self.stop_lxc(node, vmid)
        elif vm_type == "qemu":
            return self.stop_qemu(node, vmid)
        else:
            raise ProxmoxAPIError(f"Unknown VM type: {vm_type}")

    def get_vm_status(self, node: str, vmid: int, vm_type: str = "lxc") -> dict:
        """Get VM/LXC status."""
        if vm_type == "lxc":
            return self.get_lxc_status(node, vmid)
        elif vm_type == "qemu":
            return self.get_qemu_status(node, vmid)
        else:
            raise ProxmoxAPIError(f"Unknown VM type: {vm_type}")

    def is_configured(self) -> bool:
        """Check if API is properly configured."""
        return bool(self.host and self.auth_header)

    # ==================== Task Methods ====================

    def get_task_status(self, node: str, upid: str) -> dict:
        """Get status of a task."""
        return self.get(f"nodes/{node}/tasks/{upid}/status")

    def wait_for_task(
        self,
        node: str,
        upid: str,
        timeout: int = 300,
        interval: float = 2.0,
    ) -> dict:
        """
        Wait for a task to complete.

        Args:
            node: Node name
            upid: Task UPID
            timeout: Maximum wait time in seconds
            interval: Poll interval in seconds

        Returns:
            Final task status

        Raises:
            ProxmoxAPIError: If task fails or times out
        """
        start_time = time.time()

        while True:
            status = self.get_task_status(node, upid)

            if status.get("status") == "stopped":
                if status.get("exitstatus") == "OK":
                    return status
                else:
                    raise ProxmoxAPIError(
                        f"Task failed: {status.get('exitstatus')}",
                        response=status,
                    )

            if time.time() - start_time > timeout:
                raise ProxmoxAPIError(f"Task timeout after {timeout}s")

            time.sleep(interval)


# Global instance
_proxmox_api: Optional[ProxmoxAPI] = None


def get_proxmox_api(
    host: str = None,
    user: str = None,
    token_name: str = None,
    token_value: str = None,
    **kwargs,
) -> Optional[ProxmoxAPI]:
    """Get or create the global Proxmox API instance."""
    global _proxmox_api
    if host and user and token_name and token_value:
        _proxmox_api = ProxmoxAPI(
            host=host,
            user=user,
            token_name=token_name,
            token_value=token_value,
            **kwargs,
        )
    return _proxmox_api


def init_proxmox_from_config(config: "ProxmoxConfig") -> Optional[ProxmoxAPI]:
    """Initialize Proxmox API from config object."""
    if not config.enabled or not config.host:
        return None

    return get_proxmox_api(
        host=config.host,
        user=config.user,
        token_name=config.token_name,
        token_value=config.token_value,
        port=config.port,
        verify_ssl=config.verify_ssl,
    )
