"""Перетворення NDJSON-запису (нода або термін) на чанки для Qdrant.

Принцип: чанкуємо ПО ПОЛЯХ (мітка = семантична секція), а не сліпим вікном.
Кожен чанк несе title + мітку поля + URL у payload, щоб відповідь агента
завжди мала посилання.
"""

import uuid

import config

URL_PREFIXES = ("http://", "https://", "www.")


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _as_list(value):
    return value if isinstance(value, list) else []


def _point_id(*parts):
    """Детермінований UUID — повторний інжест перезаписує той самий чанк."""
    raw = ":".join(str(p) for p in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def split_long(text, max_chars=config.MAX_CHARS, overlap=config.OVERLAP):
    """Ріже довгий текст на під-чанки по абзацах із перекриттям."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= max_chars:
            current = (current + "\n" + para).strip()
            continue
        if current:
            chunks.append(current)
        tail = current[-overlap:] if (overlap and current) else ""
        current = (tail + "\n" + para).strip() if tail else para
        # Якщо один абзац довший за ліміт — жорстко ділимо.
        while len(current) > max_chars:
            chunks.append(current[:max_chars])
            current = current[max_chars - overlap:]
    if current:
        chunks.append(current)
    return chunks


def _base_payload(rec, refs, attrs):
    base = {
        "doc_type": rec.get("type"),
        "entity": rec.get("entity"),
        "ref_id": rec.get("id"),
        "title": rec.get("title", ""),
        "url": rec.get("url", ""),
        "lang": "uk",
    }
    if rec.get("entity") == "t":
        # Термін (ДР / група ДР) — поля для фільтрів.
        base["vid"] = rec.get("vid")
        group = refs.get("field_him_sklad") or []
        base["group_tid"] = group[0] if group else None
        base["prep_tup"] = refs.get("field_preparat_tup", [])
        base["xarakter"] = refs.get("field_prep_xarakter", [])
        base["formula"] = attrs.get("formula")
        base["class_safety"] = attrs.get("field_class_safety")
        base["bees_safety"] = attrs.get("field_bees_safety")
    else:
        # Нода — рослини, з якими пов'язана (для фільтра «хвороби картоплі»).
        base["linked_plants"] = refs.get("field_rosl", [])
        base["refs"] = refs
    return base


def _make(rec, base, field, part, text):
    payload = dict(base)
    payload["field"] = field
    payload["part"] = part
    payload["text"] = text
    return {
        "id": _point_id(rec["type"], rec["id"], field, part),
        "text": text,
        "payload": payload,
    }


def chunk_record(rec):
    """Повертає список чанків {id, text, payload} для одного запису."""
    text_fields = _as_dict(rec.get("text"))
    aliases = _as_list(rec.get("aliases"))
    refs = _as_dict(rec.get("refs"))
    attrs = _as_dict(rec.get("attrs"))
    title = rec.get("title", "")

    base = _base_payload(rec, refs, attrs)
    if aliases:
        base["aliases"] = aliases

    out = []

    # 1) Опис терміна (ДР / група).
    desc = rec.get("description")
    if isinstance(desc, str) and desc.strip():
        for i, part in enumerate(split_long(desc)):
            out.append(_make(rec, base, "Опис", i, f"{title} — Опис\n{part}"))

    # 2) Текстові поля ноди/терміна.
    for label, value in text_fields.items():
        if not isinstance(value, str) or not value.strip():
            continue
        val = value.strip()
        # Пропускаємо поля-посилання («Посилання на сайт», «Джерело»).
        if val.lower().startswith(URL_PREFIXES) and len(val) < 200:
            continue
        for i, part in enumerate(split_long(val)):
            out.append(_make(rec, base, label, i, f"{title} — {label}\n{part}"))

    # 3) Чанк назв/синонімів — щоб торгові назви (Пульсар → Імазамокс) знаходились.
    if aliases:
        names = f"{title}. Інші назви: " + ", ".join(aliases)
        out.append(_make(rec, base, "Назви", 0, names))

    # 4) Фолбек: термін без опису й тексту — все одно індексуємо назву.
    if not out:
        txt = title if not aliases else f"{title}. " + ", ".join(aliases)
        out.append(_make(rec, base, "Назва", 0, txt))

    return out
