"""Allow this local runtime to reach only loopback and configured model endpoints."""
import ipaddress
import socket
from urllib.parse import urlsplit


def install_model_network_policy(endpoints, *, sockets=socket):
    allowed = set()
    for endpoint in endpoints:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Invalid configured model endpoint')
        allowed.add((parsed.hostname.lower().rstrip('.'), parsed.port or (443 if parsed.scheme == 'https' else 80)))
    resolved = set()
    original_lookup = sockets.getaddrinfo
    original_connect = sockets.socket.connect
    original_connect_ex = sockets.socket.connect_ex

    def host_text(host):
        return (host.decode('ascii') if isinstance(host, bytes) else str(host)).lower().rstrip('.')

    def loopback(host):
        if host == 'localhost':
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def lookup(host, port, *args, **kwargs):
        name = host_text(host)
        if host is not None and not loopback(name) and name not in {h for h, _ in allowed}:
            if not any(name == ip for ip, _ in resolved):
                raise PermissionError('Endpoint is not an enabled model provider')
        result = original_lookup(host, port, *args, **kwargs)
        for provider_host, provider_port in allowed:
            if name == provider_host:
                resolved.update((item[4][0], provider_port) for item in result)
        return result

    def check(address):
        if not isinstance(address, tuple):
            return  # Unix-domain sockets are not external network connections.
        host, port = host_text(address[0]), address[1]
        if not loopback(host) and (host, port) not in allowed and (host, port) not in resolved:
            raise PermissionError('Endpoint is not an enabled model provider')

    def connect(self, address):
        check(address)
        return original_connect(self, address)

    def connect_ex(self, address):
        check(address)
        return original_connect_ex(self, address)

    sockets.getaddrinfo = lookup
    sockets.socket.connect = connect
    sockets.socket.connect_ex = connect_ex
