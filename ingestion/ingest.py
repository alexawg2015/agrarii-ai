"""Інжест корпусу в Qdrant.

Використання (з кореня проєкту):
    python ingestion/ingest.py                 # усі знайдені .ndjson
    python ingestion/ingest.py dr malady       # лише вказані типи
    python ingestion/ingest.py --recreate      # перестворити колекції з нуля
"""

import argparse
import glob
import json
import os
import sys
from itertools import islice

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

import config
from chunking import chunk_record

client_oa = OpenAI(api_key=config.OPENAI_API_KEY)
client_qd = QdrantClient(url=config.QDRANT_URL)


def batched(iterable, size):
    iterator = iter(iterable)
    while True:
        batch = list(islice(iterator, size))
        if not batch:
            return
        yield batch


def ensure_collection(name, recreate=False):
    exists = client_qd.collection_exists(name)
    if exists and recreate:
        client_qd.delete_collection(name)
        exists = False
    if not exists:
        client_qd.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=config.EMBED_DIM, distance=Distance.COSINE),
        )


def embed(texts):
    resp = client_oa.embeddings.create(
        model=config.EMBED_MODEL,
        input=texts,
        dimensions=config.EMBED_DIM,
    )
    return [item.embedding for item in resp.data]


def load_chunks(ndjson_path):
    chunks = []
    with open(ndjson_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            chunks.extend(chunk_record(json.loads(line)))
    return chunks


def ingest_file(path, recreate=False):
    typ = os.path.splitext(os.path.basename(path))[0]
    collection = config.COLLECTIONS.get(typ)
    if not collection:
        print(f"  ! пропуск '{typ}': немає колекції в config.COLLECTIONS")
        return

    ensure_collection(collection, recreate=recreate)
    chunks = load_chunks(path)
    print(f"  {typ}: {len(chunks)} чанків → колекція '{collection}'")

    for batch in tqdm(list(batched(chunks, config.EMBED_BATCH)), desc=f"  {typ}", unit="batch"):
        vectors = embed([c["text"] for c in batch])
        points = [
            PointStruct(id=c["id"], vector=vec, payload=c["payload"])
            for c, vec in zip(batch, vectors)
        ]
        client_qd.upsert(collection_name=collection, points=points)


def main():
    parser = argparse.ArgumentParser(description="Інжест аграрного корпусу в Qdrant.")
    parser.add_argument("types", nargs="*", help="типи для інжесту (порожньо = всі)")
    parser.add_argument("--recreate", action="store_true", help="перестворити колекції з нуля")
    args = parser.parse_args()

    if not config.OPENAI_API_KEY:
        sys.exit("Не задано OPENAI_API_KEY у .env")

    files = sorted(glob.glob(os.path.join(config.EXPORT_DIR, "*.ndjson")))
    if args.types:
        wanted = set(args.types)
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0] in wanted]
    if not files:
        sys.exit(f"Не знайдено .ndjson у {config.EXPORT_DIR}")

    # Перестворюємо кожну колекцію лише один раз (кілька типів → одна колекція).
    recreated = set()
    for path in files:
        typ = os.path.splitext(os.path.basename(path))[0]
        collection = config.COLLECTIONS.get(typ)
        do_recreate = args.recreate and collection is not None and collection not in recreated
        if collection:
            recreated.add(collection)
        print(f"→ {os.path.basename(path)}")
        ingest_file(path, recreate=do_recreate)

    print("Готово.")


if __name__ == "__main__":
    main()
