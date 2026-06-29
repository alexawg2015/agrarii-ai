"""Інструменти структурного підбору (HTTP до Drupal: resolve / pidbir)."""

import re

import requests
from langchain_core.tools import tool

import settings

API = settings.AGRO_API_BASE.rstrip("/")


def _strip(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


@tool
def find_object(name: str, kind: str) -> str:
    """Знаходить код об'єкта для підбору препаратів.

    kind: 'cult' — культура; 'enemy' — шкідник/хвороба/бур'ян; 'dr' — діюча речовина.
    Повертає варіанти з кодами (напр. n1327). Цей code передавай у select_preparations.
    Якщо варіантів кілька — вибери найдоречніший або уточни в користувача.
    """
    try:
        resp = requests.get(f"{API}/agrorag-api/resolve", params={"qr": name, "kind": kind}, timeout=20)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"Помилка запиту resolve: {exc}"

    results = data.get("results", [])
    if not results:
        return f"Не знайдено об'єкта за назвою «{name}» (kind={kind})."
    lines = []
    for item in results[:8]:
        extra = ""
        matched = item.get("matched")
        if matched and matched != "title":
            extra = f"  (за назвою: {matched})"
        lines.append(f"{item['title']} → code={item['code']}{extra}")
    return "\n".join(lines)


@tool
def select_preparations(cult: str = "", enemy: str = "", dr: str = "", type: str = "") -> str:
    """Підбирає РЕАЛЬНІ препарати проти ворога на культурі (з нормами й посиланнями).

    cult, enemy — коди з find_object (напр. 'n1327', 'n2064').
    dr — tid(и) діючих речовин через '-' (необов'язково). type — tid призначення (необов'язково).
    Норми, дози, способи обробки бери ЛИШЕ з відповіді цього інструмента — не вигадуй.
    У відповіді завжди давай посилання на препарати та на повний підбір.
    """
    params = {k: v for k, v in {"cult": cult, "enemy": enemy, "dr": dr, "type": type}.items() if v}
    if not params:
        return "Потрібно вказати хоча б культуру, ворога або діючу речовину (коди з find_object)."
    try:
        resp = requests.get(f"{API}/agrorag-api/pidbir", params=params, timeout=60)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return f"Помилка запиту pidbir: {exc}"

    if data.get("error"):
        return data["error"]

    total = data.get("total", 0)
    items = data.get("preparats", [])[:8]
    cult_t = ", ".join(_strip(x) for x in data.get("cult", []))
    enemy_t = ", ".join(_strip(x) for x in data.get("enemy", []))

    out = [
        f"Знайдено препаратів: {total} (показано {len(items)}).",
        f"Культура: {cult_t or '—'} | Ворог: {enemy_t or '—'}",
        f"Повний підбір на сайті: {data.get('pidbir_url', '')}",
        "",
    ]
    for p in items:
        norms = []
        for z in p.get("zastosuvannya", []):
            n = z.get("norma_vutrat", {}) or {}
            rng = n.get("text") or "–".join([v for v in [n.get("ot"), n.get("do")] if v])
            piece = f"норма {rng}" if rng else ""
            if z.get("sposib_obrobky"):
                piece += " (" + ", ".join(z["sposib_obrobky"]) + ")"
            if z.get("strok_do_zboru"):
                piece += f", строк до збору врожаю {z['strok_do_zboru']} дн."
            piece = piece.strip().strip(",")
            if piece:
                norms.append(piece)
        norms_s = "; ".join(norms[:2])
        dr_s = ", ".join(p.get("dr", []))
        type_s = ", ".join(p.get("type", []))
        out.append(f"• {p['title']} — {dr_s} [{type_s}]. {norms_s}".rstrip())
        out.append(f"  {p['url']}")
    return "\n".join(out)
