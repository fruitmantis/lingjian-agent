"""Synthetic model/provider fixtures; no legacy model connection writes."""
import os
from backend.app.routers import model_config

def create_model(**values):
    provider_id=values.pop('providerId',None)
    if provider_id is None:
        provider=model_config.create_provider(model_config.ProviderCreate(
            name=values.pop('provider','OpenAI Compatible'),
            baseUrl=values.pop('baseUrl',None) or os.getenv('LLM_BASE_URL','https://api.deepseek.com'),
            apiKey=values.pop('apiKey',None)))
        provider_id=provider.id
    return model_config.create_config(model_config.ModelConfigCreate(providerId=provider_id,**values))
