"""Konektor generik OpenAI-compatible — 1 file untuk semua cloud LLM.

Space Bunny, Muse Spark (Meta Model API), OpenRouter, Groq, dll
semuanya ngomong format OpenAI: POST {base}/chat/completions.
Kunci API TIDAK PERNAH ke frontend — cuma hidup di backend/.env.
"""
import json
import time
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseLlmProvider

SYSTEM_LAPORAN = (
    "Kamu asisten POS konter HP B_gadget. Jawab bahasa Indonesia santai, singkat, maksimal 8 baris. "
    "HANYA pakai angka dari DATA JSON yang diberikan. Jangan mengarang angka/nama. "
    "Uang format Rp (contoh Rp 1.500.000). "
    "Jika omzet dikunci (locked), sampaikan bahwa akun teknisi tidak boleh lihat omzet. "
    "Tutup dengan 1 saran aksi konkret (mis. follow-up yang telat / restock part)."
)


class OpenAICompatProvider(BaseLlmProvider):
    """Provider generik. Beda vendor = beda base_url + key + model, kode sama."""

    def __init__(
        self,
        pid: str,
        label: str,
        base_url: str,
        api_key: str = "",
        model: str = "",
        extra_body: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
        chat_timeout: float = 60.0,
    ):
        self.name = pid  # id registry, mis. space-bunny
        self.label = label
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.extra_body = extra_body or {}
        self.timeout = timeout
        self.chat_timeout = chat_timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def list_models(self) -> List[str]:
        return [self.model] if self.model else []

    def health_check(self) -> Dict[str, Any]:
        t0 = time.perf_counter()
        if not self.configured:
            return {
                "ok": False, "provider": self.name, "label": self.label,
                "reachable": False, "latency_ms": 0,
                "model": self.model, "configured": False,
                "hint": f"Isi key di backend/.env dulu ({self.name.upper()}_KEY)",
            }
        try:
            r = httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            r.raise_for_status()
            return {
                "ok": True, "provider": self.name, "label": self.label,
                "reachable": True, "latency_ms": latency_ms,
                "model": self.model, "configured": True, "hint": None,
            }
        except Exception as e:
            return {
                "ok": False, "provider": self.name, "label": self.label,
                "reachable": False, "latency_ms": int((time.perf_counter() - t0) * 1000),
                "model": self.model, "configured": True,
                "error": f"{type(e).__name__}: {e}",
                "hint": "Cek base_url / key / koneksi internet",
            }

    def ask(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not self.configured:
            raise RuntimeError(f"Model {self.label} belum dikonfigurasi (key kosong di .env)")
        body: Dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "temperature": 0.2,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": SYSTEM_LAPORAN},
                {"role": "user", "content": f"Pertanyaan: {prompt}\nDATA: {json.dumps(context or {}, ensure_ascii=False)[:6000]}\nJawab sekarang."},
            ],
        }
        body.update(self.extra_body)
        r = httpx.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body, timeout=self.chat_timeout)
        r.raise_for_status()
        data = r.json()
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            raise RuntimeError(f"Respon tak dikenal dari {self.label}: {str(data)[:300]}")
