"""Serve the isolated snapshot; deny non-loopback network traffic before importing app."""
import ipaddress
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env', override=False)
private = ROOT / '.isolation/runtime'
for key in ('LINGJIAN_DATABASE_PATH', 'LINGJIAN_UPLOADS_DIR', 'LINGJIAN_CHROMA_DIR'):
    value = Path(os.environ[key])
    if not value.resolve().is_relative_to(private) or value.is_symlink():
        raise RuntimeError('Isolated runtime paths must remain inside this worktree')
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex

def check(address):
    if isinstance(address, tuple):
        try:
            allowed = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            allowed = address[0] == 'localhost'
        if not allowed:
            raise PermissionError('External network disabled in isolated snapshot runtime')

def connect(self, address):
    check(address)
    return original_connect(self, address)

def connect_ex(self, address):
    check(address)
    return original_connect_ex(self, address)

socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=8100)
