"""Provider Ollama (lokal, gratis) — Fase 0+1.

Health check = GET /api/tags (ringan, tanpa load model).
ask() = POST /api/chat (Fase 1 laporan). extract() baru Fase 2.
Hanya pakai httpx (sudah ada di requirements) + stdlib.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseLlmProvider


class OllamaProvider(BaseLlmProvider):
    name = "ollama"

    def __init__(
        self,
        host: str = "http://localhost:11434",
        text_model: str = "qwen2.5:7b",
        vision_model: str = "llama3.2-vision:11b",
        timeout: float = 10.0,
    ):
        self.host = (host or "http://localhost:11434").rstrip("/")
        self.text_model = text_model
        self.vision_model = vision_model
        self.timeout = timeout

    def list_models(self) -> List[str]:
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    def ask(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Fase 1: rangkum DATA JSON jadi bahasa santai. Wajib pakai angka dari DATA."""
        chat_timeout = float(os.getenv("AI_TIMEOUT_CHAT", "60"))
        system = (
            "Kamu asisten POS konter HP B_gadget. Jawab bahasa Indonesia santai, singkat, maksimal 8 baris. "
            "HANYA pakai angka dari DATA JSON yang diberikan. Jangan mengarang angka/nama. "
            "Uang format Rp (contoh Rp 1.500.000). "
            "Jika omzet dikunci (locked), sampaikan bahwa akun teknisi tidak boleh lihat omzet. "
            "Tutup dengan 1 saran aksi konkret (mis. follow-up yang telat / restock part)."
        )
        user = f"Pertanyaan: {prompt}\nDATA: {json.dumps(context or {}, ensure_ascii=False)[:6000]}\nJawab sekarang."
        r = httpx.post(
            f"{self.host}/api/chat",
            json={
                "model": self.text_model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {"temperature": 0.2, "num_predict": 350},
            },
            timeout=chat_timeout,
        )
        r.raise_for_status()
        return (r.json().get("message", {}).get("content", "") or "").strip()

    def health_check(self) -> Dict[str, Any]:
        t0 = time.perf_counter()
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=self.timeout)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            r.raise_for_status()
            data = r.json()
            available = [m.get("name", "") for m in data.get("models", [])]

            def _present(want: str) -> bool:
                w = (want or "").lower()
                base = w.split(":")[0]
                return any(w in (a or "").lower() or (a or "").lower().startswith(base + ":") for a in available)

            return {
                "ok": True,
                "provider": self.name,
                "host": self.host,
                "reachable": True,
                "latency_ms": latency_ms,
                "text_model": self.text_model,
                "vision_model": self.vision_model,
                "text_present": _present(self.text_model),
                "vision_present": _present(self.vision_model),
                "models_available": available,
                "hint": (
                    None
                    if (_present(self.text_model) and _present(self.vision_model))
                    else f"ollama pull {self.text_model} / ollama pull {self.vision_model}"
                ),
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "ok": False,
                "provider": self.name,
                "host": self.host,
                "reachable": False,
                "latency_ms": latency_ms,
                "text_model": self.text_model,
                "vision_model": self.vision_model,
                "text_present": False,
                "vision_present": False,
                "models_available": [],
                "error": f"{type(e).__name__}: {e}",
                "hint": "Pastikan Ollama jalan: `ollama serve` lalu `ollama pull qwen2.5:7b`",
            }
