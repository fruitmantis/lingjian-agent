"""Dedicated development Runtime entrypoint."""
from .server import create_app
app=create_app("development")
