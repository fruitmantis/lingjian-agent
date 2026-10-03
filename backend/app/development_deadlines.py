"""Task deadlines derived from the accepted development execution policy."""
from .model_timeout_settings import get_settings


def run_timeout(execution=None):
    return get_settings(agent_id='partner_development',execution=execution).run_budget()
