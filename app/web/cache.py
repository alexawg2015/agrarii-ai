"""Семантичний кеш питань-відповідей на Qdrant з TTL та КОНТЕКСТОМ.

Ключ влучання: висока схожість ПИТАННЯ + збіг context_hash (хеш попередньої
розмови). Це дозволяє безпечно кешувати ланцюжки: «а препарати?» після
діагнозу A і після діагнозу B — різні записи, бо різний контекст.
"""

import json
import time
import uuid

from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchValue, PointStruct, Range, VectorParams,
)

import settings
from clients import qd, embed_query

COLLECTION = settings.CACHE_COLLECTION


def ensure_collection():
    if not qd.collection_exists(COLLECTION):
        qd.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=settings.EMBED_DIM, distance=Distance.COSINE),
        )


def lookup(query, context_hash):
    try:
        vector = embed_query(query)
        min_ts = time.time() - settings.CACHE_TTL
        hits = qd.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=1,
            query_filter=Filter(must=[
                FieldCondition(key="created_at", range=Range(gte=min_ts)),
                FieldCondition(key="ctx", match=MatchValue(value=context_hash)),
            ]),
        ).points
    except Exception:  # noqa: BLE001
        return None

    if not hits or hits[0].score < settings.CACHE_THRESHOLD:
        return None
    payload = hits[0].payload or {}
    return {
        "answer": payload.get("answer", ""),
        "trace": json.loads(payload.get("trace", "[]")),
        "score": round(hits[0].score, 3),
    }


def store(query, answer, trace, context_hash):
    try:
        vector = embed_query(query)
        qd.upsert(
            collection_name=COLLECTION,
            points=[PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "query": query,
                    "answer": answer,
                    "trace": json.dumps(trace, ensure_ascii=False),
                    "ctx": context_hash,
                    "created_at": time.time(),
                },
            )],
        )
    except Exception:  # noqa: BLE001
        pass
