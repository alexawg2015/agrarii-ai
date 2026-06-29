"""FastAPI-шар навколо swarm (STATELESS + підписана історія).

Клієнт зберігає історію + HMAC-підпис (sig). Сервер перевіряє цілісність,
банить при підробці, веде розмову з повним контекстом і кешує ланцюжки.

Пайплайн /api/chat:
  бан? → HMAC(history)==sig? → injection-guard → дешевий ліміт →
  кеш(питання+context_hash) → (промах) дорогий ліміт → swarm(історія+питання)
  → новий sig → метрики.

Запуск (з каталогу app/):
    cd app
    uvicorn web.main:app --host 0.0.0.0 --port 8000
"""

import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import settings
from web import cache, guards, integrity, metrics, ratelimit
from web.runner import run_chat

app = FastAPI(title="Agrarii AI", version="2.0")


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)


@app.on_event("startup")
def _startup():
    cache.ensure_collection()


class ChatIn(BaseModel):
    message: str
    client_id: str | None = None
    history: list[dict] | None = None
    sig: str | None = None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/metrics")
def get_metrics():
    return metrics.snapshot()


@app.post("/api/metrics/reset")
def reset_metrics():
    metrics.reset()
    return {"status": "reset"}


def _new_sig(history, user_msg, answer):
    new_history = list(history) + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": answer},
    ]
    return integrity.sign(new_history)


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    client_id = body.client_id or "anon"
    history = body.history or []
    message = (body.message or "").strip()
    metrics.incr("requests_total")

    if not message:
        return JSONResponse({"error": "Порожнє повідомлення."}, status_code=400)

    # 0) Бан.
    if metrics.is_banned(client_id):
        return JSONResponse(
            {"error": "Доступ тимчасово обмежено через підозрілу активність."},
            status_code=403,
        )

    # 1) Цілісність історії (HMAC). Підробка → бан + лічильник + скидання.
    if not integrity.verify(history, body.sig):
        metrics.incr("tamper")
        metrics.ban_client(client_id, settings.TAMPER_BAN_TTL)
        return JSONResponse(
            {"error": "Порушено цілісність історії розмови. Почнімо заново.", "reset": True},
            status_code=409,
        )

    # 2) Захист від інʼєкцій (поточне повідомлення).
    blocked, reason = guards.check_injection(message)
    if blocked:
        metrics.incr("blocked_injection")
        answer = guards.REFUSAL_MESSAGE
        return JSONResponse({
            "answer": answer, "blocked": True, "reason": reason,
            "sig": _new_sig(history, message, answer),
        }, status_code=400)

    # 3) Загальний (дешевий) ліміт.
    ok, retry = ratelimit.allow_cheap(ip)
    if not ok:
        metrics.incr("rate_limited")
        return JSONResponse(
            {"error": "Забагато запитів. Спробуйте трохи згодом.", "retry_after": retry},
            status_code=429, headers={"Retry-After": str(retry)},
        )

    ctx = integrity.context_hash(history)

    # 4) Семантичний кеш (з урахуванням контексту → безпечно для ланцюжків).
    cached = cache.lookup(message, ctx)
    if cached:
        metrics.incr("cache_hit")
        metrics.record(message, cached["answer"], cached=True, latency_ms=0)
        return {
            "answer": cached["answer"], "trace": cached["trace"], "cached": True,
            "score": cached.get("score"), "sig": _new_sig(history, message, cached["answer"]),
        }
    metrics.incr("cache_miss")

    # 5) Дорогий ліміт (LLM).
    ok, retry = ratelimit.allow_llm(ip)
    if not ok:
        metrics.incr("rate_limited")
        return JSONResponse(
            {"error": "Ліміт звернень до асистента вичерпано. Спробуйте згодом.", "retry_after": retry},
            status_code=429, headers={"Retry-After": str(retry)},
        )

    # 6) Swarm з повною історією.
    started = time.time()
    try:
        result = run_chat(history, message)
    except Exception as exc:  # noqa: BLE001
        metrics.incr("errors")
        return JSONResponse({"error": f"Помилка обробки: {exc}"}, status_code=500)
    latency_ms = (time.time() - started) * 1000
    metrics.incr("llm_calls")
    metrics.observe_latency(latency_ms)

    ans_low = (result.get("answer") or "").lower()
    if "лише з питаннями захисту рослин" in ans_low:
        metrics.incr("refused_scope")

    metrics.record(
        message, result["answer"], cached=False, latency_ms=latency_ms,
        tokens_in=result.get("tokens_in", 0), tokens_out=result.get("tokens_out", 0),
        agents=result.get("agents", []),
    )

    if result["answer"]:
        cache.store(message, result["answer"], result["trace"], ctx)

    return {
        "answer": result["answer"], "trace": result["trace"], "cached": False,
        "latency_ms": round(latency_ms), "sig": _new_sig(history, message, result["answer"]),
    }


# Статика (фронтенд).
_STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=_STATIC, html=True), name="static")
