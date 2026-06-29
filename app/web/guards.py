"""Захист від prompt-injection (як у Занятті 19: direct / Base64 / ROT13 / reverse)."""

import base64
import codecs
import re

# Сигнатури прямих інʼєкцій (укр + англ).
INJECTION_PATTERNS = [
    r"ігнор(уй|уйте|увати)",
    r"забудь( про)? (попередн|усі|все|інструкц)",
    r"забудь .{0,20}інструкц",
    r"не зважай на (попередн|інструкц|правил)",
    r"ти тепер\b",
    r"віднині ти\b",
    r"систем(ний|на) (промпт|інструкц)",
    r"розкрий (свій )?(промпт|систем|інструкц)",
    r"(яку|який) (версі|модел)",
    r"(яка|що за) (модель|версія)",
    r"ти (часом )?(chatgpt|gpt|клод|claude|джипіті|чатджпт)",
    r"твій (промпт|систем|інструкц|розробник|провайдер)",
    r"ignore\s+(all|the|previous|prior|above|any)",
    r"disregard\s+(all|the|previous|prior|above|any)",
    r"forget\s+(all|the|previous|everything|prior)",
    r"override\s+(the\s+)?(instructions|prompt|system)",
    r"you are now\b",
    r"act as\b",
    r"system prompt",
    r"reveal (your )?(prompt|instructions|system)",
    r"\bjailbreak\b",
    r"\bDAN\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def _has_injection(text):
    return any(rx.search(text) for rx in _COMPILED)


def _try_base64(text):
    """Декодуємо base64-фрагменти (з відновленням padding) і перевіряємо на інʼєкцію."""
    # Цілий рядок як кандидат + окремі довгі токени.
    candidates = re.findall(r"[A-Za-z0-9+/]{16,}={0,2}", text)
    stripped = text.strip()
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    for token in candidates:
        cleaned = re.sub(r"[^A-Za-z0-9+/=]", "", token)
        if len(cleaned) < 12:
            continue
        # відновлюємо padding до кратності 4
        pad = (-len(cleaned)) % 4
        cleaned_padded = cleaned + ("=" * pad)
        try:
            decoded = base64.b64decode(cleaned_padded).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            continue
        if decoded and _has_injection(decoded):
            return True
    return False


def _try_rot13(text):
    try:
        return _has_injection(codecs.decode(text, "rot_13"))
    except Exception:  # noqa: BLE001
        return False


def _try_reverse(text):
    return _has_injection(text[::-1])


def check_injection(text):
    """Повертає (blocked: bool, reason: str)."""
    text = text or ""
    if _has_injection(text):
        return True, "direct"
    if _try_base64(text):
        return True, "base64"
    if _try_rot13(text):
        return True, "rot13"
    if _try_reverse(text):
        return True, "reverse"
    return False, ""


REFUSAL_MESSAGE = (
    "Вибач, це питання виглядає як спроба змінити мої інструкції. "
    "Я можу допомогти з діагностикою хвороб/шкідників рослин і підбором препаратів."
)
