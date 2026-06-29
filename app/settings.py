"""Налаштування застосунку (читає .env з кореня проєкту)."""

import os
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
load_dotenv(os.path.join(ROOT, ".env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")
EMBED_DIM = int(os.getenv("EMBED_DIM", "3072"))
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# Розумна модель для агентів. Можна змінити через CHAT_MODEL у .env.
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o")

# База Drupal-сайту з JSON API (resolve / pidbir).
AGRO_API_BASE = os.getenv("AGRO_API_BASE", "http://agrarii")

# --- Веб-шар (FastAPI) ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Семантичний кеш (Qdrant). Поріг високий: різні вороги/культури
# семантично близькі, тож не хочемо віддати чужу відповідь.
CACHE_COLLECTION = os.getenv("CACHE_COLLECTION", "qa_cache")
CACHE_THRESHOLD = float(os.getenv("CACHE_THRESHOLD", "0.95"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "86400"))  # секунди

# Dual rate-limit (вікно у секундах + ліміти на IP).
RL_WINDOW = int(os.getenv("RL_WINDOW", "60"))
RL_CHEAP_LIMIT = int(os.getenv("RL_CHEAP_LIMIT", "60"))      # відповіді з кешу/легкі
RL_LLM_LIMIT = int(os.getenv("RL_LLM_LIMIT", "15"))          # звернення до LLM (дорогі)

# Орієнтовна ціна токенів (для оцінки $). Дефолт — приблизно gpt-4o, $ за 1K.
LLM_PRICE_IN = float(os.getenv("LLM_PRICE_IN", "0.0025"))
LLM_PRICE_OUT = float(os.getenv("LLM_PRICE_OUT", "0.01"))

# Секрет для підпису історії (HMAC). ОБОВʼЯЗКОВО задай свій у .env для продакшну.
HISTORY_SECRET = os.getenv("HISTORY_SECRET", "change-me-dev-secret")
# Бан клієнта при підробці історії (секунди).
TAMPER_BAN_TTL = int(os.getenv("TAMPER_BAN_TTL", "600"))
