"""Network utility functions for IP validation and calculation."""

import ipaddress
import re


def netmask_to_prefix(netmask: str) -> int:
    """Convert netmask (255.255.255.0) to prefix length (24).

    Args:
        netmask: Netmask string like "255.255.255.0"

    Returns:
        Prefix length (0-32), or 0 on error
    """
    try:
        parts = [int(p) for p in netmask.split('.')]
        if len(parts) != 4:
            return 0
        binary = ''.join(format(p, '08b') for p in parts)
        return binary.count('1')
    except (ValueError, AttributeError):
        return 0


def prefix_to_netmask(prefix: int) -> str:
    """Convert prefix length (24) to netmask (255.255.255.0).

    Args:
        prefix: CIDR prefix length (0-32)

    Returns:
        Netmask string like "255.255.255.0"
    """
    try:
        if not 0 <= prefix <= 32:
            return "255.255.255.0"
        mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
        return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"
    except (ValueError, TypeError):
        return "255.255.255.0"


def get_network_prefix_string(network_ip: str, prefix: int) -> str:
    """Get the fixed network prefix string based on subnet.

    Args:
        network_ip: Network IP like "192.168.1.0"
        prefix: CIDR prefix length

    Returns:
        Fixed prefix string like "192.168.1."
    """
    try:
        octets = network_ip.split('.')
        if len(octets) != 4:
            return "192.168.1."

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


def get_default_host_parts(prefix: int) -> dict[str, str]:
    """Get default host parts based on prefix length.

    Args:
        prefix: CIDR prefix length

    Returns:
        Dict with "gateway" and "traefik" host parts
    """
    if prefix >= 24:
        return {"gateway": "1", "traefik": "10"}
    elif prefix >= 16:
        return {"gateway": "0.1", "traefik": "0.10"}
    elif prefix >= 8:
        return {"gateway": "0.0.1", "traefik": "0.0.10"}
    else:
        return {"gateway": "1", "traefik": "10"}


def is_ip_in_subnet(ip_str: str, network_ip: str, prefix: int) -> bool:
    """Check if an IP address is within a subnet.

    Args:
        ip_str: IP to check like "192.168.1.50"
        network_ip: Network IP like "192.168.1.0"
        prefix: CIDR prefix length

    Returns:
        True if IP is in subnet
    """
    try:
        network = ipaddress.ip_network(f"{network_ip}/{prefix}", strict=False)
        ip = ipaddress.ip_address(ip_str)
        return ip in network
    except (ValueError, TypeError):
        return False


def is_valid_ip(ip_str: str) -> bool:
    """Validate an IP address string.

    Args:
        ip_str: IP address to validate

    Returns:
        True if valid IPv4 address
    """
    try:
        ipaddress.ip_address(ip_str)
        return True
    except (ValueError, TypeError):
        return False


def is_valid_cidr(cidr: str) -> bool:
    """Validate a CIDR notation string.

    Args:
        cidr: CIDR string like "192.168.1.0/24"

    Returns:
        True if valid CIDR
    """
    try:
        ipaddress.ip_network(cidr, strict=False)
        return True
    except (ValueError, TypeError):
        return False


def parse_cidr(cidr: str) -> tuple[str, int] | None:
    """Parse a CIDR string into network IP and prefix.

    Args:
        cidr: CIDR string like "192.168.1.0/24"

    Returns:
        Tuple of (network_ip, prefix) or None on error
    """
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return str(network.network_address), network.prefixlen
    except (ValueError, TypeError):
        return None


def get_network_from_ip(ip_str: str, prefix: int) -> str:
    """Get network address from an IP and prefix.

    Args:
        ip_str: IP address like "192.168.1.50"
        prefix: CIDR prefix length

    Returns:
        Network address like "192.168.1.0"
    """
    try:
        network = ipaddress.ip_network(f"{ip_str}/{prefix}", strict=False)
        return str(network.network_address)
    except (ValueError, TypeError):
        return ip_str


def is_valid_hostname(hostname: str) -> bool:
    """Validate a hostname.

    Args:
        hostname: Hostname to validate

    Returns:
        True if valid hostname
    """
    if not hostname or len(hostname) > 253:
        return False

    # Allow single-label hostnames and FQDNs
    pattern = re.compile(
        r'^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.?$'
    )
    return bool(pattern.match(hostname))


def is_valid_mac(mac: str) -> bool:
    """Validate a MAC address.

    Args:
        mac: MAC address to validate (AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF)

    Returns:
        True if valid MAC address
    """
    if not mac:
        return True  # Empty is allowed (optional)

    pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
    return bool(pattern.match(mac))
