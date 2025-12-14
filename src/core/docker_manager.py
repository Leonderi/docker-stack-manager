"""Docker and Docker Compose management on remote VMs."""

from dataclasses import dataclass
from typing import Optional

from .config_loader import VMConfig
from .ssh_manager import SSHManager, get_ssh_manager


@dataclass
class ContainerStatus:
    """Status of a Docker container."""
    name: str
    image: str
    status: str
    ports: str
    running: bool


@dataclass
class StackStatus:
    """Status of a Docker Compose stack."""
    name: str
    path: str
    containers: list[ContainerStatus]
    running: bool


class DockerManager:
    """Manages Docker operations on remote VMs."""

    def __init__(self, ssh_manager: Optional[SSHManager] = None):
        """Initialize Docker manager."""
        self.ssh = ssh_manager or get_ssh_manager()

    def is_docker_installed(self, vm: VMConfig) -> bool:
        """Check if Docker is installed on the VM."""
        result = self.ssh.run_command(vm, "docker --version")
        return result.success

    def is_compose_installed(self, vm: VMConfig) -> bool:
        """Check if Docker Compose is installed on the VM."""
        # Try docker compose (v2) first
        result = self.ssh.run_command(vm, "docker compose version")
        if result.success:
            return True
        # Fall back to docker-compose (v1)
        result = self.ssh.run_command(vm, "docker-compose --version")
        return result.success

    def get_docker_version(self, vm: VMConfig) -> Optional[str]:
        """Get Docker version on the VM."""
        result = self.ssh.run_command(vm, "docker --version")
        if result.success:
            return result.stdout
        return None

    def install_docker(self, vm: VMConfig) -> tuple[bool, str]:
        """Install Docker on the VM using official script."""
        commands = [
            "curl -fsSL https://get.docker.com -o /tmp/get-docker.sh",
            "sh /tmp/get-docker.sh",
            "systemctl enable docker",
            "systemctl start docker",
            "rm /tmp/get-docker.sh"
        ]

        for cmd in commands:
            result = self.ssh.run_command(vm, cmd)
            if not result.success:
                return False, f"Failed at: {cmd}\n{result.stderr}"

        return True, "Docker installed successfully"

    def get_running_containers(self, vm: VMConfig) -> list[ContainerStatus]:
        """Get list of running containers on the VM."""
        result = self.ssh.run_command(
            vm,
            "docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'"
        )

        containers = []
        if result.success and result.stdout:
            for line in result.stdout.split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        containers.append(ContainerStatus(
                            name=parts[0],
                            image=parts[1],
                            status=parts[2],
                            ports=parts[3],
                            running=True
                        ))
        return containers

    def get_all_containers(self, vm: VMConfig) -> list[ContainerStatus]:
        """Get list of all containers on the VM."""
        result = self.ssh.run_command(
            vm,
            "docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'"
        )

        containers = []
        if result.success and result.stdout:
            for line in result.stdout.split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        running = "Up" in parts[2]
                        containers.append(ContainerStatus(
                            name=parts[0],
                            image=parts[1],
                            status=parts[2],
                            ports=parts[3],
                            running=running
                        ))
        return containers

    def compose_up(
        self,
        vm: VMConfig,
        stack_path: str,
        detach: bool = True
    ) -> tuple[bool, str]:
        """Run docker compose up for a stack."""
        cmd = f"cd {stack_path} && docker compose up"
        if detach:
            cmd += " -d"

        result = self.ssh.run_command(vm, cmd)
        if result.success:
            return True, result.stdout
        return False, result.stderr

    def compose_down(
        self,
        vm: VMConfig,
        stack_path: str,
        remove_volumes: bool = False
    ) -> tuple[bool, str]:
        """Run docker compose down for a stack."""
        cmd = f"cd {stack_path} && docker compose down"
        if remove_volumes:
            cmd += " -v"

        result = self.ssh.run_command(vm, cmd)
        if result.success:
            return True, result.stdout
        return False, result.stderr

    def compose_pull(self, vm: VMConfig, stack_path: str) -> tuple[bool, str]:
        """Pull latest images for a stack."""
        cmd = f"cd {stack_path} && docker compose pull"
        result = self.ssh.run_command(vm, cmd)
        if result.success:
            return True, result.stdout
        return False, result.stderr

    def compose_logs(
        self,
        vm: VMConfig,
        stack_path: str,
        tail: int = 100,
        service: Optional[str] = None
    ) -> str:
        """Get logs from a stack."""
        cmd = f"cd {stack_path} && docker compose logs --tail={tail}"
        if service:
            cmd += f" {service}"

        result = self.ssh.run_command(vm, cmd)
        return result.stdout if result.success else result.stderr

    def compose_ps(self, vm: VMConfig, stack_path: str) -> list[ContainerStatus]:
        """Get container status for a stack."""
        cmd = f"cd {stack_path} && docker compose ps --format '{{{{.Name}}}}|{{{{.Image}}}}|{{{{.Status}}}}|{{{{.Ports}}}}'"
        result = self.ssh.run_command(vm, cmd)

        containers = []
        if result.success and result.stdout:
            for line in result.stdout.split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        running = "Up" in parts[2] or "running" in parts[2].lower()
                        containers.append(ContainerStatus(
                            name=parts[0],
                            image=parts[1],
                            status=parts[2],
                            ports=parts[3],
                            running=running
                        ))
        return containers

    def restart_container(self, vm: VMConfig, container_name: str) -> tuple[bool, str]:
        """Restart a container."""
        result = self.ssh.run_command(vm, f"docker restart {container_name}")
        if result.success:
            return True, f"Container {container_name} restarted"
        return False, result.stderr

    def stop_container(self, vm: VMConfig, container_name: str) -> tuple[bool, str]:
        """Stop a container."""
        result = self.ssh.run_command(vm, f"docker stop {container_name}")
        if result.success:
            return True, f"Container {container_name} stopped"
        return False, result.stderr

    def start_container(self, vm: VMConfig, container_name: str) -> tuple[bool, str]:
        """Start a container."""
        result = self.ssh.run_command(vm, f"docker start {container_name}")
        if result.success:
            return True, f"Container {container_name} started"
        return False, result.stderr

    def get_container_logs(
        self,
        vm: VMConfig,
        container_name: str,
        tail: int = 100
    ) -> str:
        """Get logs from a specific container."""
        result = self.ssh.run_command(vm, f"docker logs --tail={tail} {container_name}")
        return result.stdout if result.success else result.stderr

    def prune_images(self, vm: VMConfig) -> tuple[bool, str]:
        """Remove unused Docker images."""
        result = self.ssh.run_command(vm, "docker image prune -af")
        if result.success:
            return True, result.stdout
        return False, result.stderr

    def prune_volumes(self, vm: VMConfig) -> tuple[bool, str]:
        """Remove unused Docker volumes."""
        result = self.ssh.run_command(vm, "docker volume prune -f")
        if result.success:
            return True, result.stdout
        return False, result.stderr


# Global Docker manager instance
_docker_manager: Optional[DockerManager] = None


def get_docker_manager() -> DockerManager:
    """Get or create the global Docker manager instance."""
    global _docker_manager
    if _docker_manager is None:
        _docker_manager = DockerManager()
    return _docker_manager
