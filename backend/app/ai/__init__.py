"""Paket AI B_gadget — Fase 1+: multi-model.

Ollama lokal + konektor OpenAI-compatible generik (Space Bunny,
Muse Spark, custom). Ganti/tambah model = isi .env, tanpa ubah
router & frontend.
"""
from .base import BaseLlmProvider
from .factory import get_ai_config, get_provider
from .registry import default_model_id, model_registry

__all__ = ["BaseLlmProvider", "get_ai_config", "get_provider", "default_model_id", "model_registry"]
