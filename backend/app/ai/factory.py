"""Factory provider — ganti model/vendor cukup via .env.

LLM_PROVIDER=ollama      (legacy, = LLM_DEFAULT=ollama)
LLM_DEFAULT=ollama | space-bunny | muse-spark | custom
Detail per model lihat registry.py. Router Fase 1+2 lewat registry.
"""
import os
from typing import Any, Dict

from dotenv import load_dotenv

from .base import BaseLlmProvider
from .registry import default_model_id as _default_id
from .registry import get_provider as _get_provider_registry
from .registry import model_registry

load_dotenv()


def get_ai_config() -> Dict[str, Any]:
    return {
        "provider": os.getenv("LLM_PROVIDER", "ollama").strip().lower(),
        "default_model": _default_id(),
        "host": os.getenv("OLLAMA_HOST", "http://localhost:11434").strip(),
        "text_model": os.getenv("OLLAMA_TEXT", "qwen2.5:7b").strip(),
        "vision_model": os.getenv("OLLAMA_VISION", "llama3.2-vision:11b").strip(),
        "timeout": float(os.getenv("AI_TIMEOUT", "10")),
        "models": [m["id"] for m in model_registry()],
    }


def get_provider(model_id: str = "") -> BaseLlmProvider:
    # LLM_PROVIDER legacy tetap didukung: kalau di-set selain ollama, pakai itu sebagai default.
    legacy = (os.getenv("LLM_PROVIDER", "") or "").strip().lower()
    if model_id:
        return _get_provider_registry(model_id)
    if legacy and legacy != "ollama":
        return _get_provider_registry(legacy)
    return _get_provider_registry(_default_id())
