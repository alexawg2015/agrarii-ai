"""RAG-інструменти пошуку у векторній базі (по доменах)."""

from langchain_core.tools import tool

from clients import qd, embed_query


def _search(collection, query, label, limit=6, max_per_source=2):
    """Пошук у колекції → текст для LLM зі збереженням URL для цитування."""
    vector = embed_query(query)
    hits = qd.query_points(collection_name=collection, query=vector, limit=limit).points
    if not hits:
        return "Нічого не знайдено за цим запитом."
    seen, blocks = {}, []
    for hit in hits:
        p = hit.payload
        url = p.get("url", "")
        if seen.get(url, 0) >= max_per_source:
            continue
        seen[url] = seen.get(url, 0) + 1
        blocks.append(
            "{label}: {title}\nРозділ: {field}\nURL: {url}\nФрагмент: {text}\n---".format(
                label=label,
                title=p.get("title", ""),
                field=p.get("field", ""),
                url=url,
                text=(p.get("text", "") or "").strip(),
            )
        )
    return "\n".join(blocks)


@tool
def search_diseases(query: str) -> str:
    """Пошук інформації про хвороби рослин: ознаки, розвиток, поширення, заходи захисту.

    Запит формулюй українською за суттю (симптом, культура, назва хвороби).
    Повертає фрагменти з посиланнями на сторінки сайту.
    """
    return _search("diseases", query, "Хвороба")


@tool
def search_pests(query: str) -> str:
    """Пошук інформації про шкідників рослин: зовнішній вигляд, розвиток, що пошкоджують, заходи захисту.

    Запит — українською (симптом пошкодження, культура, назва шкідника).
    Повертає фрагменти з посиланнями на сторінки сайту.
    """
    return _search("pests", query, "Шкідник")


@tool
def search_preparations(query: str) -> str:
    """Пошук описової інформації про препарати: механізм дії, особливості, рекомендації.

    Корисно для питань «як діє препарат», «чим відрізняється», «який краще».
    Точний підбір препаратів за культурою/ворогом — НЕ тут, а в select_preparations.
    """
    return _search("preparations", query, "Препарат")
