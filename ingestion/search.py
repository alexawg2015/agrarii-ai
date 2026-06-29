"""Швидкий тест ретриву.

Використання:
    python ingestion/search.py diseases "скручування листя картоплі"
    python ingestion/search.py substances "системний гербіцид проти злакових"
    python ingestion/search.py preparations "фунгіцид від парші яблуні"
"""

import sys

from openai import OpenAI
from qdrant_client import QdrantClient

import config

client_oa = OpenAI(api_key=config.OPENAI_API_KEY)
client_qd = QdrantClient(url=config.QDRANT_URL)


def main():
    if len(sys.argv) < 3:
        sys.exit('Використання: python ingestion/search.py <колекція> "<запит>"')

    collection = sys.argv[1]
    query = " ".join(sys.argv[2:])

    vector = client_oa.embeddings.create(
        model=config.EMBED_MODEL,
        input=[query],
        dimensions=config.EMBED_DIM,
    ).data[0].embedding

    hits = client_qd.query_points(collection_name=collection, query=vector, limit=5).points

    print(f'\nЗапит: "{query}"  (колекція: {collection})\n')
    for hit in hits:
        p = hit.payload
        snippet = p.get("text", "").replace("\n", " ")[:160]
        print(f"[{hit.score:.3f}] {p.get('title')} — {p.get('field')}")
        print(f"        {p.get('url')}")
        print(f"        {snippet} ...\n")


if __name__ == "__main__":
    main()
