"""LLM model registry with pre-initialized instances.

Supports:
- OpenAI direct (gpt-5, gpt-5-mini, …)
- OpenRouter (300+ models via OPENAI_BASE_URL=https://openrouter.ai/api/v1)
- Veles fine-tune (Qwen2.5-32B LoRA via RunPod vLLM)

Temperature is ALWAYS sourced from settings.DEFAULT_LLM_TEMPERATURE (default 0.0).
For financial analysis temperature must be 0 to ensure deterministic output.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import Environment, settings
from app.core.logging import logger

_API_KEY = SecretStr(settings.OPENAI_API_KEY)
_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL") or None
_TEMP = settings.DEFAULT_LLM_TEMPERATURE  # 0.0 for financial analysis


def _make_llm(model: str, temperature: float = _TEMP, **extra: Any) -> ChatOpenAI:
    """Construct a ChatOpenAI instance, injecting base_url when set (OpenRouter etc.)."""
    kwargs: Dict[str, Any] = {
        "model": model,
        "api_key": _API_KEY,
        "temperature": temperature,
        "max_tokens": settings.MAX_TOKENS,
        **extra,
    }
    if _BASE_URL:
        kwargs["base_url"] = _BASE_URL
    return ChatOpenAI(**kwargs)


def _build_veles_llm() -> Optional[ChatOpenAI]:
    """Build Veles fine-tune if VELES_API_URL is configured."""
    if not settings.USE_VELES_MODEL:
        return None
    return ChatOpenAI(
        model=settings.VELES_MODEL_NAME,
        api_key=SecretStr(settings.VELES_API_KEY),
        base_url=f"{settings.VELES_API_URL.rstrip('/')}/v1",
        temperature=_TEMP,
        max_tokens=settings.MAX_TOKENS,
        streaming=True,
        stream_options={"include_usage": True},
    )


def _build_registry() -> List[Dict[str, Any]]:
    """Build the ordered model list at startup.

    Order:
    1. Veles (if configured) — highest priority custom fine-tune
    2. DEFAULT_LLM_MODEL from env — primary production/dev model
    3. Standard fallbacks (only added if not already covered by #1/#2)
    """
    entries: List[Dict[str, Any]] = []

    # 1. Veles fine-tune
    veles = _build_veles_llm()
    if veles:
        entries.append({"name": "veles", "llm": veles})

    # 2. Primary model from settings (works for any OpenAI-compatible endpoint)
    primary = settings.DEFAULT_LLM_MODEL
    if primary and primary not in {e["name"] for e in entries}:
        entries.append({"name": primary, "llm": _make_llm(primary)})
        logger.info("llm_registry_primary_model", model=primary, base_url=_BASE_URL or "openai-direct")

    # 3. Standard fallbacks — skip entirely when Veles is configured
    # (OpenRouter free tier is too slow and rate-limited to be a useful fallback)
    if not _BASE_URL and not settings.USE_VELES_MODEL:
        _token_limit: Dict[str, Any] = {"max_completion_tokens": settings.MAX_TOKENS}
        _standard_fallbacks: List[Dict[str, Any]] = [
            {
                "name": "gpt-5-mini",
                "llm": ChatOpenAI(
                    model="gpt-5-mini",
                    api_key=_API_KEY,
                    temperature=_TEMP,
                    model_kwargs=_token_limit,
                    reasoning={"effort": "low"},
                ),
            },
            {
                "name": "gpt-5",
                "llm": ChatOpenAI(
                    model="gpt-5",
                    api_key=_API_KEY,
                    temperature=_TEMP,
                    model_kwargs=_token_limit,
                    top_p=0.95 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.8,
                    presence_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
                    frequency_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
                ),
            },
            {
                "name": "gpt-5.4-nano",
                "llm": ChatOpenAI(
                    model="gpt-5.4-nano",
                    api_key=_API_KEY,
                    temperature=_TEMP,
                    model_kwargs=_token_limit,
                    reasoning={"effort": "low"},
                ),
            },
        ]
        existing_names = {e["name"] for e in entries}
        for fb in _standard_fallbacks:
            if fb["name"] not in existing_names:
                entries.append(fb)
    elif _BASE_URL and not settings.USE_VELES_MODEL:
        # OpenRouter without Veles: add free fallback models
        _openrouter_fallbacks = [
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-r1:free",
            "google/gemma-3-27b-it:free",
        ]
        existing_names = {e["name"] for e in entries}
        for model_name in _openrouter_fallbacks:
            if model_name not in existing_names:
                entries.append({"name": model_name, "llm": _make_llm(model_name)})

    return entries


class LLMRegistry:
    """Registry of available LLM models with pre-initialized instances."""

    LLMS: List[Dict[str, Any]] = _build_registry()

    @classmethod
    def get(cls, model_name: str, **kwargs: Any) -> BaseChatModel:
        """Get an LLM by name with optional argument overrides.

        When kwargs are provided a fresh ChatOpenAI instance is returned with
        those overrides applied, leaving the shared registry entry untouched.

        Args:
            model_name: Name of the model to retrieve.
            **kwargs: Optional arguments to override default model configuration.

        Returns:
            BaseChatModel instance.

        Raises:
            ValueError: If model_name is not found in LLMS.
        """
        model_entry = next((e for e in cls.LLMS if e["name"] == model_name), None)

        if not model_entry:
            available = ", ".join(e["name"] for e in cls.LLMS)
            raise ValueError(f"model '{model_name}' not found in registry. available models: {available}")

        if kwargs:
            logger.debug("creating_llm_with_custom_args", model_name=model_name, custom_args=list(kwargs.keys()))
            build_kwargs: Dict[str, Any] = {
                "temperature": _TEMP,
                "max_tokens": settings.MAX_TOKENS,
                **kwargs,
            }
            if _BASE_URL:
                build_kwargs.setdefault("base_url", _BASE_URL)
            return ChatOpenAI(model=model_name, api_key=_API_KEY, **build_kwargs)

        logger.debug("using_default_llm_instance", model_name=model_name)
        return model_entry["llm"]

    @classmethod
    def get_all_names(cls) -> List[str]:
        """Return all registered model names in order."""
        return [e["name"] for e in cls.LLMS]

    @classmethod
    def get_model_at_index(cls, index: int) -> Dict[str, Any]:
        """Return the model entry at a specific index, wrapping to 0 if out of range."""
        if 0 <= index < len(cls.LLMS):
            return cls.LLMS[index]
        return cls.LLMS[0]
