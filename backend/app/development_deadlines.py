"""Task deadlines derived from the single administrator-managed model policy."""
from .model_timeout_settings import get_settings


def run_timeout():
    return get_settings().run_budget()
