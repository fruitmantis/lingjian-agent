"""No network is opened: exercise the runtime's provider-only network boundary."""
from types import SimpleNamespace
import pytest
from backend.app.model_network_policy import install_model_network_policy


def policy(endpoints=('https://provider.test/v1',)):
    calls=[]
    class Socket:
        def connect(self, address):
            calls.append(address)
        def connect_ex(self, address):
            calls.append(address)
            return 0
    def lookup(host, port, *args, **kwargs):
        return [(2,1,6,'',('203.0.113.10',int(port or 443)))]
    sockets=SimpleNamespace(socket=Socket,getaddrinfo=lookup)
    install_model_network_policy(endpoints,sockets=sockets)
    return sockets,calls


def test_loopback_preserved_and_other_external_hosts_blocked():
    sockets,calls=policy()
    for address in [('127.0.0.1',5432),('::1',8000),('localhost',3000)]:
        sockets.socket().connect(address)
    assert len(calls)==3
    with pytest.raises(PermissionError):sockets.getaddrinfo('unconfigured.test',443)
    with pytest.raises(PermissionError):sockets.socket().connect(('203.0.113.11',443))


def test_only_provider_resolved_address_and_configured_port_allowed():
    sockets,calls=policy()
    with pytest.raises(PermissionError):sockets.socket().connect(('203.0.113.10',443))
    sockets.getaddrinfo(b'provider.test',443)
    sockets.socket().connect(('203.0.113.10',443))
    assert sockets.socket().connect_ex(('provider.test',443))==0
    with pytest.raises(PermissionError):sockets.socket().connect(('203.0.113.10',444))
    with pytest.raises(PermissionError):sockets.socket().connect_ex(('provider.test',80))
    with pytest.raises(PermissionError):sockets.getaddrinfo('provider.test.attacker.test',443)
    assert len(calls)==2


@pytest.mark.parametrize('url',['file:///tmp/model','https://user:secret@provider.test/v1','https:///bad'])
def test_invalid_endpoint_does_not_install_policy(url):
    with pytest.raises(ValueError):policy([url])
