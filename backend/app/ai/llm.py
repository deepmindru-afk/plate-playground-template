"""LiveKit Agents OpenAI LLM wiring (Chat Completions).

The frontend used the AI Gateway with provider-prefixed model ids such as
``openai/gpt-4o-mini`` or ``google/gemini-2.5-flash``. Here the provider
prefix is stripped and the request goes straight to an OpenAI-compatible
Chat Completions endpoint (LiveKit's ``openai.LLM``), authenticated with
``OPENAI_API_KEY`` (server-side) or a client-supplied ``apiKey`` fallback.
"""

from typing import Any

from livekit.plugins.openai import LLM as OpenAILLM

from .. import config


class MissingApiKeyError(Exception):
    pass


def resolve_api_key(client_key: str | None) -> str:
    """Server key wins; client key is a fallback when allowed."""
    if config.OPENAI_API_KEY:
        return config.OPENAI_API_KEY
    key = (client_key or "").strip()
    if config.ALLOW_CLIENT_API_KEY and key:
        return key
    raise MissingApiKeyError("Missing AI API key.")


def strip_provider_prefix(model: str) -> str:
    """'openai/gpt-4o-mini' -> 'gpt-4o-mini'. Ignores URLs."""
    if "/" not in model or model.startswith(("http://", "https://")):
        return model
    return model.split("/", 1)[1]


def resolve_model(
    client_model: str | None, *, fallback: str | None = None
) -> str:
    model = (client_model or "").strip()
    if not model and fallback:
        model = fallback
    if not model:
        raise MissingApiKeyError("Missing AI model.")
    return model


def create_llm(
    *,
    model: str,
    api_key: str,
    temperature: float | None = None,
) -> OpenAILLM:
    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        # max_completion_tokens is passed per-request via extra_kwargs.
        "max_retries": 0,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if config.OPENAI_BASE_URL:
        kwargs["base_url"] = config.OPENAI_BASE_URL

    return OpenAILLM(**kwargs)