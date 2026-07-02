"""LLM polish adapter (BUILD_SPEC §10).

polish(text, lang) improves fluency ONLY — it must never invent or change numbers,
place names, or facts (those come from templates). With LLM_PROVIDER=none it returns
the input unchanged, so a zero-key demo still produces full advisories.
Supported providers: anthropic (Messages API), nim / openrouter (OpenAI-compatible).
"""
from __future__ import annotations

import logging

import httpx

from backend.config import settings

log = logging.getLogger("vayunetra.advisory.llm")

_SYSTEM = (
    "You are an editor. Improve the fluency and tone of the given public-health advisory "
    "in the requested language. Keep ALL numbers, place names, times and facts exactly as given. "
    "Do not add new claims. Return only the improved text, no preamble."
)


def is_enabled() -> bool:
    return settings.llm_provider in {"anthropic", "nim", "openrouter"}


def polish(text: str, lang: str) -> str:
    """Return an LLM-polished version of text, or the input unchanged on any failure/none."""
    provider = settings.llm_provider
    try:
        if provider == "anthropic" and settings.anthropic_api_key:
            return _anthropic(text, lang)
        if provider == "nim" and settings.nim_api_key:
            return _openai_compatible(settings.nim_base_url, settings.nim_api_key,
                                      settings.nim_model, text, lang)
        if provider == "openrouter":
            import os
            key = os.getenv("OPENROUTER_API_KEY", "")
            if key:
                return _openai_compatible("https://openrouter.ai/api/v1", key,
                                          "meta-llama/llama-3.1-70b-instruct", text, lang)
    except Exception as exc:  # noqa: BLE001 - polish is best-effort; never break the advisory
        log.warning("LLM polish failed (%s); returning template text", exc)
    return text


def _anthropic(text: str, lang: str) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": "claude-sonnet-4-6", "max_tokens": 400, "system": _SYSTEM,
              "messages": [{"role": "user", "content": f"Language: {lang}\n\n{text}"}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def _openai_compatible(base_url: str, api_key: str, model: str, text: str, lang: str) -> str:
    resp = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={"model": model, "max_tokens": 400, "temperature": 0.3,
              "messages": [{"role": "system", "content": _SYSTEM},
                           {"role": "user", "content": f"Language: {lang}\n\n{text}"}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
