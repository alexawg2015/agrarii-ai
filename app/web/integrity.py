"""Цілісність історії через HMAC-підпис.

Клієнт зберігає історію + sig. Сервер підписує історію своїм секретом
(HMAC-SHA256). Клієнт не знає секрету → не може підробити підпис під
змінену історію. Перевірка ловить будь-яку зміну попередніх реплік.
"""

import hashlib
import hmac
import json

import settings

_SECRET = settings.HISTORY_SECRET.encode("utf-8")


def _canonical(history):
    """Детермінована серіалізація історії (однакова на кожному кроці)."""
    return json.dumps(
        history, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sign(history):
    """HMAC-підпис історії (hex)."""
    return hmac.new(_SECRET, _canonical(history), hashlib.sha256).hexdigest()


def verify(history, sig):
    """Чи валідний підпис. Порожня історія (перший крок) — завжди валідна."""
    if not history:
        return True
    if not sig:
        return False
    return hmac.compare_digest(sign(history), sig)


def context_hash(history):
    """Короткий хеш контексту — для кешування ланцюжків."""
    if not history:
        return "root"
    return hashlib.sha256(_canonical(history)).hexdigest()[:16]
