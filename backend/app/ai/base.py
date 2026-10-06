"""Kontrak provider LLM — Fase 0.

Fase 0 hanya butuh health_check(). ask() & extract() disiapkan
sebagai signature agar Fase 1 (laporan) & Fase 2 (vision) tidak
mengubah interface.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseLlmProvider(ABC):
    """Interface wajib semua provider (ollama, gemini, openai, ...)."""

    name: str = "base"

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Cek koneksi ke LLM. Wajib ringan (tanpa inference berat).

        Return minimal:
        {"ok": bool, "provider": str, "host": str, ...}
        """
        raise NotImplementedError

    # --- Fase 1 (belum dipakai di Fase 0, dikunci signature-nya) ---
    def ask(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError(f"{self.name} belum implement ask() (Fase 1)")

    # --- Fase 2 (belum dipakai di Fase 0, dikunci signature-nya) ---
    def extract_service(
        self, image_bytes: bytes, tipe: str = "nota"
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.name} belum implement extract_service() (Fase 2)"
        )

    def list_models(self) -> List[str]:
        return []
