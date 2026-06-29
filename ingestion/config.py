"""Конфігурація інжесту (читає .env з кореня проєкту)."""

import os
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
load_dotenv(os.path.join(ROOT, ".env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")
EMBED_DIM = int(os.getenv("EMBED_DIM", "3072"))
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EXPORT_DIR = os.getenv("EXPORT_DIR") or os.path.join(ROOT, "export")

# Параметри чанкінгу.
MAX_CHARS = 1200      # довші поля ріжемо на під-чанки
OVERLAP = 150         # перекриття між під-чанками
EMBED_BATCH = 96      # розмір батчу для OpenAI embeddings
UPSERT_BATCH = 256    # запас на майбутнє (зараз upsert батчимо по EMBED_BATCH)

# Тип ноди/терміна (= ім'я NDJSON-файлу) → колекція Qdrant (= домен агента).
COLLECTIONS = {
    "malady": "diseases",
    "gr_rosl_hvorobu": "diseases",
    "shkidnuku": "pests",
    "byrjan": "plants",
    "byrjan1": "plants",
    "kultura": "plants",
    "preparatu": "preparations",
    "dr": "substances",
    "dr_group": "substances",
}
