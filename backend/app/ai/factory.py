from app.ai.base import LLMProvider
from app.ai.cloudflare import CloudflareProvider
from app.ai.gemini import GeminiProvider
from app.ai.groq import GroqProvider
from app.core.runtime_settings import get_runtime_settings


def get_llm_provider() -> LLMProvider:
    """Create the configured LLM provider without leaking provider details."""

    settings = get_runtime_settings()
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if provider == "groq":
        return GroqProvider(settings.groq_api_key, settings.groq_model)
    if provider == "cloudflare":
        return CloudflareProvider(settings.cloudflare_account_id, settings.cloudflare_api_token, settings.cloudflare_model)
    raise RuntimeError(f"Unsupported LLM provider: {provider}")
