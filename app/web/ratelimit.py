"""Dual rate-limit на Redis: окремі ліміти для дешевих (кеш) і дорогих (LLM) запитів.

Фіксоване вікно (INCR + EXPIRE) — простий і надійний патерн.
"""

import redis

import settings

_r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _hit(bucket, ip, limit, window):
    """Повертає (allowed: bool, retry_after: int)."""
    key = f"agro:rl:{bucket}:{ip}"
    try:
        current = _r.incr(key)
        if current == 1:
            _r.expire(key, window)
        if current > limit:
            ttl = _r.ttl(key)
            return False, (ttl if ttl and ttl > 0 else window)
        return True, 0
    except Exception:  # noqa: BLE001
        # Якщо Redis недоступний — не блокуємо (fail-open).
        return True, 0


def allow_cheap(ip):
    """Загальний ліміт на будь-який запит (захист від DDoS)."""
    return _hit("cheap", ip, settings.RL_CHEAP_LIMIT, settings.RL_WINDOW)


def allow_llm(ip):
    """Суворіший ліміт на звернення до LLM (захист від витрат)."""
    return _hit("llm", ip, settings.RL_LLM_LIMIT, settings.RL_WINDOW)
