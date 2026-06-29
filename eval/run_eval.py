"""Eval-пайплайн агро-асистента (4 типи перевірок).

1) Deterministic — наявність очікуваних посилань/змісту (contains_any/not_empty),
   блокування інʼєкцій (blocked), відмова на off-topic (refused_or_empty).
2) Retrieval — RAG recall@5 / recall@10: чи правильна нода у топ-k прямого пошуку.
3) LLM-as-Judge — relevancy + faithfulness (чи відповідь на те питання й заземлена).
4) Підсумок + вердикт SHIP/NO-SHIP → REPORT.md.

Чесні метрики: усе отримано реальним прогоном. «Істина» для recall задана
вручну в golden.json (поле relevant) — це нормально й необхідно для recall.

Запуск (з каталогу app/):
    cd app
    python ../eval/run_eval.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

import settings                       # noqa: E402
from clients import qd, embed_query   # noqa: E402
from web import guards                # noqa: E402
from web.runner import run_chat       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden.json")
REPORT = os.path.join(HERE, "REPORT.md")

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-4o-mini")
RELEVANCY_THRESHOLD = 0.7
FAITHFULNESS_THRESHOLD = 0.7


# ---------- 2) RETRIEVAL: recall@k ----------
def retrieval_hits(collection, query, k=10):
    """Повертає список URL з топ-k прямого пошуку у Qdrant."""
    try:
        vector = embed_query(query)
        pts = qd.query_points(collection_name=collection, query=vector, limit=k).points
        return [(p.payload or {}).get("url", "") for p in pts]
    except Exception:  # noqa: BLE001
        return []


def recall_at_k(urls, relevant, k):
    top = urls[:k]
    for rel in relevant:
        if any(rel.lower() in (u or "").lower() for u in top):
            return 1
    return 0


# ---------- 3) LLM-AS-JUDGE ----------
def judge(query, answer):
    """Повертає (relevancy, faithfulness) у [0..1] або (None, None) при помилці."""
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = (
        "Ти — суворий оцінювач відповідей агро-асистента. Оціни ВІДПОВІДЬ на ПИТАННЯ.\n"
        "relevancy: чи відповідь стосується саме цього питання (а не іншого), 0..1.\n"
        "faithfulness: чи відповідь спирається на конкретику (назви, посилання, норми) "
        "без вигадок, 0..1.\n"
        "Поверни СУВОРО JSON: {\"relevancy\": x, \"faithfulness\": y} без пояснень.\n\n"
        f"ПИТАННЯ: {query}\n\nВІДПОВІДЬ: {answer}\n"
    )
    try:
        resp = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "")
        data = json.loads(raw)
        return float(data.get("relevancy", 0)), float(data.get("faithfulness", 0))
    except Exception:  # noqa: BLE001
        return None, None


# ---------- 1) DETERMINISTIC ----------
def deterministic(case, answer, blocked):
    check = case["check"]
    if check == "blocked":
        return blocked, ("заблоковано" if blocked else "НЕ заблоковано (очікувалось)")
    if blocked:
        return False, "несподівано заблоковано"
    low = (answer or "").lower()
    if check == "not_empty":
        return len(low.strip()) > 0, f"довжина={len(answer)}"
    if check == "refused_or_empty":
        ok = ("лише з питаннями захисту рослин" in low) or (len(low.strip()) == 0)
        return ok, ("відмовлено" if ok else "відповів на off-topic")
    if check == "contains_any":
        hit = next((e for e in case["expect"] if e.lower() in low), None)
        return hit is not None, (f"знайдено «{hit}»" if hit else "не знайдено очікуваного")
    return False, f"невідома перевірка: {check}"


def main():
    cases = json.load(open(GOLDEN, encoding="utf-8"))
    rows = []
    passed = 0
    by_cat = {}

    # агрегати retrieval / judge
    r5_hits = r10_hits = r_total = 0
    rel_sum = faith_sum = j_total = 0
    j_pass = 0

    print(f"Прогін {len(cases)} кейсів...\n")
    for case in cases:
        query = case["query"]
        blocked, _ = guards.check_injection(query)

        # відповідь (крім явно заблокованих)
        answer = ""
        if not blocked and case["check"] != "blocked":
            try:
                answer = run_chat([], query).get("answer", "") or ""
            except Exception as exc:  # noqa: BLE001
                answer = f"[ERROR: {exc}]"

        # 1) deterministic
        ok, detail = deterministic(case, answer, blocked)
        passed += ok
        cat = case["category"]
        by_cat.setdefault(cat, [0, 0])
        by_cat[cat][0] += ok
        by_cat[cat][1] += 1

        # 2) recall@k (де є істина)
        rec = ""
        if case.get("relevant") and case.get("collection"):
            urls = retrieval_hits(case["collection"], query, k=10)
            h5 = recall_at_k(urls, case["relevant"], 5)
            h10 = recall_at_k(urls, case["relevant"], 10)
            r5_hits += h5
            r10_hits += h10
            r_total += 1
            rec = f"R@5={h5} R@10={h10}"

        # 3) LLM-judge (де позначено)
        jud = ""
        if case.get("judge") and answer and not answer.startswith("[ERROR"):
            rel, faith = judge(query, answer)
            if rel is not None:
                rel_sum += rel
                faith_sum += faith
                j_total += 1
                jp = rel >= RELEVANCY_THRESHOLD and faith >= FAITHFULNESS_THRESHOLD
                j_pass += jp
                jud = f"rel={rel:.2f} faith={faith:.2f} {'PASS' if jp else 'FAIL'}"

        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {case['id']} — {detail}" + (f" | {rec}" if rec else "") + (f" | {jud}" if jud else ""))
        rows.append((case, ok, detail, rec, jud))

    total = len(cases)
    rate = round(100 * passed / total, 1) if total else 0
    recall5 = round(100 * r5_hits / r_total, 1) if r_total else 0
    recall10 = round(100 * r10_hits / r_total, 1) if r_total else 0
    avg_rel = round(rel_sum / j_total, 3) if j_total else 0
    avg_faith = round(faith_sum / j_total, 3) if j_total else 0
    judge_rate = round(100 * j_pass / j_total, 1) if j_total else 0
    verdict = "SHIP" if rate >= 80 else "NO-SHIP"

    lines = [
        "# Eval Report — Agrarii AI",
        "",
        f"**Deterministic: {passed}/{total} ({rate}%) → {verdict}**",
        "",
        "## Зведені метрики",
        "",
        "| Метрика | Значення |",
        "|---|---|",
        f"| Deterministic pass rate | {rate}% ({passed}/{total}) |",
        f"| RAG recall@5 | {recall5}% ({r5_hits}/{r_total}) |",
        f"| RAG recall@10 | {recall10}% ({r10_hits}/{r_total}) |",
        f"| LLM-Judge relevancy (сер.) | {avg_rel} |",
        f"| LLM-Judge faithfulness (сер.) | {avg_faith} |",
        f"| LLM-Judge pass rate | {judge_rate}% ({j_pass}/{j_total}) |",
        "",
        "## За категоріями",
        "",
        "| Категорія | Deterministic |",
        "|---|---|",
    ]
    for cat, (p, n) in by_cat.items():
        lines.append(f"| {cat} | {p}/{n} |")

    lines += ["", "## Кейси", "", "| ID | Тип | Det | Retrieval | LLM-Judge |", "|---|---|---|---|---|"]
    for case, ok, detail, rec, jud in rows:
        lines.append(f"| {case['id']} | {case.get('type','')} | {'PASS' if ok else 'FAIL'} | {rec or '—'} | {jud or '—'} |")

    lines += [
        "",
        "## Методологія (4 типи перевірок)",
        "- **Deterministic** — наявність очікуваних посилань/змісту, блокування інʼєкцій, відмова на off-topic.",
        "- **Retrieval (recall@k)** — чи правильна нода у топ-5/10 прямого векторного пошуку (істина задана вручну в golden.json).",
        "- **LLM-as-Judge** — relevancy (чи на те питання) + faithfulness (чи без вигадок), пороги ≥ 0.70.",
        "- **Категорії**: golden / regression / adversarial.",
        "",
        f"_Суддя: {JUDGE_MODEL}. Усі метрики — реальний прогін, нічого не змодельовано вручну (окрім розмітки істини для recall)._",
    ]
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))

    print(f"\n=== ПІДСУМОК ===")
    print(f"Deterministic: {passed}/{total} ({rate}%) → {verdict}")
    print(f"Recall@5: {recall5}%  Recall@10: {recall10}%")
    print(f"LLM-Judge: relevancy {avg_rel}, faithfulness {avg_faith}, pass {judge_rate}%")
    print(f"Звіт: {REPORT}")


if __name__ == "__main__":
    main()
