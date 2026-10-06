"""Router AI — Fase 0: health. Fase 1: tanya laporan (read-only, multi-model)."""
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.factory import get_ai_config, get_provider
from ..ai.registry import default_model_id, model_registry
from ..ai.tools import detect_intent, fallback_answer, gather
from ..database import get_db
from ..store_ctx import resolve_store, store_role
from .auth import get_current_user

router = APIRouter(prefix="/ai", tags=["AI"])

VALID_MODELS = ("ollama", "space-bunny", "muse-spark", "custom")


@router.get("/health")
def ai_health(model: Optional[str] = Query(None), current=Depends(get_current_user)):
    """Cek backend -> LLM. ?model=ollama|space-bunny|muse-spark|custom (default dari .env)."""
    if not current:
        raise HTTPException(status_code=401, detail="Token tidak valid / belum login")
    cfg = get_ai_config()
    try:
        provider = get_provider(model or "")
    except NotImplementedError as e:
        return {"ok": False, "config": cfg, "error": str(e)}
    result = provider.health_check()
    result["config"] = cfg
    result["model"] = (model or default_model_id())
    return result


@router.get("/models")
def ai_models(current=Depends(get_current_user)):
    """Daftar model untuk dropdown widget. Key tidak pernah dibocorkan."""
    if not current:
        raise HTTPException(status_code=401, detail="Token tidak valid / belum login")
    return {"default": default_model_id(), "models": model_registry()}


class AskIn(BaseModel):
    q: Optional[str] = None
    query: Optional[str] = None
    store_id: Optional[int] = None
    model: Optional[str] = None


@router.post("/ask")
def ai_ask(
    body: AskIn,
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Fase 1 — jawab laporan dari data read-only + LLM rangkum.

    Aman: SELECT only (via ai.tools), scope per toko, teknisi tidak
    boleh lihat omzet. Kalau LLM/key mati -> fallback template (tetap 200).
    Body boleh bawa {"q": "...", "model": "space-bunny"}.
    """
    if not current:
        raise HTTPException(status_code=401, detail="Token tidak valid / belum login")
    question = (body.q or body.query or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pertanyaan kosong (isi q/query)")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Pertanyaan kepanjangan (maks 500 karakter)")
    want_model = (body.model or "").strip().lower() or default_model_id()
    if want_model not in VALID_MODELS:
        raise HTTPException(status_code=400, detail=f"Model tidak dikenal. Pilih: {list(VALID_MODELS)}")
    sid = body.store_id if body.store_id is not None else store_id
    store = resolve_store(db, current, sid)
    store_id_eff = store.id if store is not None else None
    role = store_role(db, current, store)

    t0 = time.perf_counter()
    intents = detect_intent(question)
    data = gather(db, intents, store_id_eff, role, current)
    try:
        answer = get_provider(want_model).ask(question, data).strip()
        source = f"llm:{want_model}"
        if not answer:
            raise RuntimeError("LLM kosong")
    except Exception as e:
        extra = ""
        if "belum dikonfigurasi" in str(e):
            extra = " Isi key-nya di backend/.env dulu ya."
        answer = fallback_answer(data, role) + f"\n\n(mode ringkas: {want_model} offline.{extra})"
        source = f"fallback:{want_model}: {type(e).__name__}"
    return {
        "answer": answer,
        "intents": intents,
        "data": data,
        "source": source,
        "model": want_model,
        "store_id": store_id_eff,
        "role": role,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
    }
