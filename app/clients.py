"""Спільні клієнти OpenAI та Qdrant."""

from openai import OpenAI
from qdrant_client import QdrantClient

import settings

oa = OpenAI(api_key=settings.OPENAI_API_KEY)
qd = QdrantClient(url=settings.QDRANT_URL)


def embed_query(text):
    """Ембеддинг одного запиту (тією самою моделлю, що й корпус)."""
    resp = oa.embeddings.create(
        model=settings.EMBED_MODEL,
        input=[text],
        dimensions=settings.EMBED_DIM,
    )
    return resp.data[0].embedding
