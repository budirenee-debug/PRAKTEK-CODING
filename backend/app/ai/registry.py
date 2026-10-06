"""Registry model — daftar yang tampil di dropdown widget.

Gratisan dulu (default): ollama lokal + space-bunny (free preview).
Muse Spark aktif tapi butuh key berbayar — tampil dengan badge 🔑.
Slot custom buat 'yang lainnya' (Groq/OpenRouter/Gemini) tinggal isi .env.
"""
import os
from typing import Any, Dict, List

from dotenv import load_dotenv

from .base import BaseLlmProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

load_dotenv()


def _f(key: str, default: str) -> str:
    return (os.getenv(key, default) or default).strip()


def model_registry() -> List[Dict[str, Any]]:
    """Daftar model untuk dropdown. Key tidak pernah ikut — cuma flag configured."""
    ollama = OllamaProvider(
        host=_f("OLLAMA_HOST", "http://localhost:11434"),
        text_model=_f("OLLAMA_TEXT", "qwen2.5:7b"),
        vision_model=_f("OLLAMA_VISION", "llama3.2-vision:11b"),
        timeout=float(os.getenv("AI_TIMEOUT", "10")),
    )
    sb_key = os.getenv("SPACEBUNNY_KEY", "").strip()
    meta_key = os.getenv("META_API_KEY", "").strip()
    custom_key = os.getenv("CUSTOM_LLM_KEY", "").strip()
    custom_base = _f("CUSTOM_LLM_BASE_URL", "")
    custom_model = _f("CUSTOM_LLM_MODEL", "")
    custom_label = _f("CUSTOM_LLM_LABEL", "Custom")
    return [
        {"id": "ollama", "label": f"Ollama lokal ({ollama.text_model})",
         "provider": "ollama", "free": True, "needs_key": False,
         "configured": True, "hint": "Offline, gratis"},
        {"id": "space-bunny", "label": "Space Bunny Alpha (1M konteks)",
         "provider": "openai-compat", "free": True, "needs_key": True,
         "configured": bool(sb_key),
         "hint": "Free preview — ambil key di spacebunny.app lalu isi SPACEBUNNY_KEY" if not sb_key else None},
        {"id": "muse-spark", "label": "Muse Spark 1.2 (Meta)",
         "provider": "openai-compat", "free": False, "needs_key": True,
         "configured": bool(meta_key),
         "hint": "Berbayar — isi META_API_KEY dari dev.meta.ai" if not meta_key else None},
        {"id": "custom", "label": f"{custom_label} (custom)",
         "provider": "openai-compat", "free": False, "needs_key": True,
         "configured": bool(custom_base and custom_model and custom_key),
         "hint": "Isi CUSTOM_LLM_* di .env untuk Groq/OpenRouter/Gemini" if not (custom_base and custom_model and custom_key) else None},
    ]


def default_model_id() -> str:
    return (os.getenv("LLM_DEFAULT", "ollama") or "ollama").strip().lower()


def get_provider(model_id: str = "") -> BaseLlmProvider:
    """Bangun provider untuk 1 model id. Raise NotImplementedError/RuntimError yg jelas."""
    mid = (model_id or default_model_id()).strip().lower()
    chat_to = float(os.getenv("AI_TIMEOUT_CHAT", "60"))
    to = float(os.getenv("AI_TIMEOUT", "10"))
    if mid == "ollama":
        return OllamaProvider(
            host=_f("OLLAMA_HOST", "http://localhost:11434"),
            text_model=_f("OLLAMA_TEXT", "qwen2.5:7b"),
            vision_model=_f("OLLAMA_VISION", "llama3.2-vision:11b"),
            timeout=to,
        )
    if mid in ("space-bunny", "spacebunny", "bunny"):
        return OpenAICompatProvider(
            pid="space-bunny", label="Space Bunny Alpha",
            base_url=_f("SPACEBUNNY_BASE_URL", "https://spacebunny.app/api/v1"),
            api_key=os.getenv("SPACEBUNNY_KEY", "").strip(),
            model=_f("SPACEBUNNY_MODEL", "space-bunny"),
            extra_body={"reasoning": {"effort": "low"}},
            timeout=to, chat_timeout=chat_to,
        )
    if mid in ("muse-spark", "muse", "muse-spark-1.2"):
        return OpenAICompatProvider(
            pid="muse-spark", label="Muse Spark 1.2",
            base_url=_f("META_BASE_URL", "https://api.meta.ai/v1"),
            api_key=os.getenv("META_API_KEY", "").strip(),
            model=_f("META_MODEL", "muse-spark-1.2"),
            timeout=to, chat_timeout=chat_to,
        )
    if mid == "custom":
        return OpenAICompatProvider(
            pid="custom", label=_f("CUSTOM_LLM_LABEL", "Custom"),
            base_url=_f("CUSTOM_LLM_BASE_URL", ""),
            api_key=os.getenv("CUSTOM_LLM_KEY", "").strip(),
            model=_f("CUSTOM_LLM_MODEL", ""),
            timeout=to, chat_timeout=chat_to,
        )
    valid = [m["id"] for m in model_registry()]
    raise NotImplementedError(f"Model '{model_id}' tidak dikenal. Pilih: {valid}")
