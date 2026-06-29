"""Метрики на Redis: лічильники + розбивка по агентах, токени/$, часовий ряд,
топ питань, останні діалоги."""

import json
import time

import redis

import settings

_r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

P = "agro:metrics:"          # лічильники
P_AGENT = "agro:agents"      # hash: ярлик → к-сть
P_TS = "agro:ts:"            # часовий ряд (по хвилинах)
P_RECENT = "agro:recent"     # список останніх діалогів
P_TOP = "agro:top"           # zset частоти питань

COUNTERS = [
    "requests_total", "cache_hit", "cache_miss",
    "blocked_injection", "refused_scope", "tamper", "rate_limited", "llm_calls", "errors",
]


def is_banned(client_id):
    try:
        return bool(_r.exists(f"agro:ban:{client_id}"))
    except Exception:  # noqa: BLE001
        return False


def ban_client(client_id, ttl):
    try:
        _r.setex(f"agro:ban:{client_id}", ttl, "1")
    except Exception:  # noqa: BLE001
        pass


# --- прості лічильники ---
def incr(name, amount=1):
    try:
        _r.incrby(P + name, amount)
    except Exception:  # noqa: BLE001
        pass


def observe_latency(ms):
    try:
        pipe = _r.pipeline()
        pipe.incrbyfloat(P + "latency_sum_ms", ms)
        pipe.incr(P + "latency_count")
        pipe.execute()
    except Exception:  # noqa: BLE001
        pass


# --- збагачені записи ---
def record(query, answer, cached, latency_ms, tokens_in=0, tokens_out=0, agents=None):
    """Єдина точка запису багатих метрик (викликається на кожен запит)."""
    try:
        # часовий ряд по хвилинах (живе ~70 хв)
        minute = int(time.time() // 60)
        ts_key = f"{P_TS}{minute}"
        _r.incr(ts_key)
        _r.expire(ts_key, 4200)

        # топ питань
        _r.zincrby(P_TOP, 1, query[:120])

        # останні діалоги
        item = {
            "q": query[:160],
            "a": (answer or "")[:160],
            "cached": bool(cached),
            "latency_ms": round(latency_ms),
            "agents": agents or [],
            "ts": int(time.time()),
        }
        _r.lpush(P_RECENT, json.dumps(item, ensure_ascii=False))
        _r.ltrim(P_RECENT, 0, 19)

        # токени та агенти — лише для реальних звернень до LLM
        if not cached:
            if tokens_in:
                _r.incrby(P + "tokens_in", tokens_in)
            if tokens_out:
                _r.incrby(P + "tokens_out", tokens_out)
            for label in (agents or []):
                _r.hincrby(P_AGENT, label, 1)
    except Exception:  # noqa: BLE001
        pass


def _timeseries(minutes=60):
    now = int(time.time() // 60)
    out = []
    for i in range(minutes - 1, -1, -1):
        m = now - i
        out.append(int(_r.get(f"{P_TS}{m}") or 0))
    return out


def snapshot():
    data = {name: int(_r.get(P + name) or 0) for name in COUNTERS}

    lat_sum = float(_r.get(P + "latency_sum_ms") or 0)
    lat_cnt = int(_r.get(P + "latency_count") or 0)
    data["avg_latency_ms"] = round(lat_sum / lat_cnt, 1) if lat_cnt else 0

    total = data["cache_hit"] + data["cache_miss"]
    data["cache_hit_rate"] = round(100 * data["cache_hit"] / total, 1) if total else 0

    tin = int(_r.get(P + "tokens_in") or 0)
    tout = int(_r.get(P + "tokens_out") or 0)
    data["tokens_in"] = tin
    data["tokens_out"] = tout
    cost = tin / 1000 * settings.LLM_PRICE_IN + tout / 1000 * settings.LLM_PRICE_OUT
    data["cost_usd"] = round(cost, 4)

    data["agents"] = {k: int(v) for k, v in (_r.hgetall(P_AGENT) or {}).items()}
    data["timeseries"] = _timeseries(60)

    top = _r.zrevrange(P_TOP, 0, 7, withscores=True)
    data["top_questions"] = [{"q": q, "n": int(s)} for q, s in top]

    recent = _r.lrange(P_RECENT, 0, 9)
    data["recent"] = [json.loads(x) for x in recent]

    return data


def reset():
    keys = _r.keys("agro:*")
    if keys:
        _r.delete(*keys)


def mark_session_seen(session_id):
    """Позначає сесію як бачену. Повертає True, якщо це ПЕРШЕ звернення сесії."""
    try:
        added = _r.sadd("agro:sessions", session_id)
        _r.expire("agro:sessions", 86400)
        return bool(added)  # 1 → новий елемент → перше звернення
    except Exception:  # noqa: BLE001
        return True
