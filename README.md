# Agrarii AI — мультиагентний AI-асистент аграрного сайту

Асистент із захисту рослин для українського аграрного сайту (на PHP): діагностика
хвороб і шкідників, підбір препаратів проти ворога на культурі з **реальними нормами**
та посиланнями на сторінки сайту.

**Ключова ідея — гібридна архітектура:**
- **описове** (ознаки, заходи захисту, опис діючих речовин) → векторний пошук (RAG, Qdrant);
- **точне** (підбір препаратів, норми витрат, реєстрація) → структурний JSON-ендпоінт
  сайту, що обгортає **рідну** бізнес-логіку підбору препаратів.

> Норми витрат **ніколи не ембедяться** — лише з БД через ендпоінт. Це виключає
> галюцинації в безпеково-критичних даних (дозування пестицидів).

---

## Архітектура

Повна цільова схема. Кольором/позначкою показано стан реалізації:
**✅ реалізовано · 🟡 частково · ⬜ заплановано**.

```mermaid
flowchart TB
    U["Користувач"] --> WEB

    subgraph WEB["Веб-шар FastAPI [OK]"]
        GUARD["Injection-guard [OK]"]
        HMAC["Підписана історія HMAC + tamper-бан [OK]"]
        RL["Dual rate-limit: кеш vs LLM [OK]"]
        CACHE["Семантичний кеш з контекстом [OK]"]
        MET["Метрики: токени, вартість, агенти [OK]"]
    end

    WEB --> SWARM

    subgraph SWARM["LangGraph Swarm [OK]"]
        AD["Агент Хвороби [OK]"]
        AP["Агент Шкідники [partial]"]
        APR["Агент Препарати [OK]"]
        AD <--> AP
        AD <--> APR
        AP <--> APR
    end

    SWARM --> RAG
    SWARM --> API

    subgraph RAG["Векторний пошук Qdrant"]
        CD["diseases [OK]"]
        CP["pests [TODO]"]
        CPL["plants [TODO]"]
        CPR["preparations [partial]"]
        CS["substances [TODO]"]
    end

    subgraph API["Структурний ендпоінт сайту [OK]"]
        RESOLVE["resolve: назва в код ноди [OK]"]
        PIDBIR["pidbir: підбір препаратів + норми [OK]"]
    end

    API --> DB[(MySQL)]
    RAG --> OAI["OpenAI embeddings"]
    SWARM --> OAI2["OpenAI gpt-4o"]
    EVAL["Eval: recall@k + LLM-Judge [OK]"] --> SWARM
```

> Позначки стану: **[OK]** реалізовано · **[partial]** частково · **[TODO]** заплановано.

### Що реалізовано зараз

| Компонент | Стан | Примітка |
|---|---|---|
| Веб-шар FastAPI (чат + метрики) | ✅ | окремий фронт, темна тема, анімований трейс |
| LangGraph swarm з handoff | ✅ | агенти Хвороби / Шкідники / Препарати |
| RAG-колекція `diseases` | ✅ | проінжещена, працює (recall@5 — див. eval) |
| Структурний підбір `pidbir` | ✅ | реальні норми (напр. Суперкіл 440 — 0,75 л/га) |
| Injection-guard | ✅ | direct / Base64 / ROT13 / reverse + SCOPE-відмови |
| Підписана історія (HMAC) + tamper-бан | ✅ | stateless-бекенд, захист від підміни контексту |
| Семантичний кеш (з контекстом) | ✅ | кешування ланцюжків через context_hash |
| Dual rate-limit (кеш vs LLM) | ✅ | Redis token-bucket, 429 + Retry-After |
| Метрики (токени, $, агенти, графік) | ✅ | вкладка дашборда |
| Eval (recall@k + LLM-Judge) | ✅ | golden set, REPORT.md, вердикт SHIP |
| RAG-колекції `pests`/`plants`/`substances` | ⬜ | **наступний крок** (код інжесту готовий) |
| Агент «Шкідники» (повноцінний RAG) | 🟡 | логіка є; чекає інжесту `pests` |
| Variety-ноди (22 000 сортів) | ⬜ | відкладено на майбутнє |

> **Чесно про межі:** наразі проінжещена лише колекція `diseases`. Тому питання про
> шкідників поки веде RAG-агент «Хвороби», а підбір препаратів проти шкідників працює
> через **структурний** ендпоінт (де норми точні). Код інжесту (`ingestion/`) уже
> підтримує всі п'ять доменів — увімкнення `pests`/`plants`/`substances` зводиться до
> прогону інжесту відповідних NDJSON. Це заплановано як найближче розширення.

---

## Структура проєкту

```
agrarii-ai/
├── docker-compose.yml         # Qdrant + Redis
├── requirements.txt
├── .env.example
├── ingestion/                 # інжест корпусу в Qdrant
│   ├── config.py              # мапа типів нод → колекцій (усі 5 доменів)
│   ├── chunking.py
│   ├── ingest.py
│   └── search.py              # ручна перевірка ретриву
├── app/
│   ├── settings.py
│   ├── clients.py
│   ├── chat.py                # CLI-чат (для розробки)
│   ├── tools/
│   │   ├── rag.py             # search_diseases / pests / preparations
│   │   └── agro_api.py        # find_object / select_preparations (Drupal API)
│   ├── agents/
│   │   └── swarm.py           # LangGraph swarm + промпти + SCOPE-правило
│   └── web/                   # FastAPI-шар
│       ├── main.py            # пайплайн запиту
│       ├── guards.py          # injection-guard
│       ├── integrity.py       # HMAC-підпис історії
│       ├── cache.py           # семантичний кеш (контекстний)
│       ├── ratelimit.py       # dual rate-limit
│       ├── metrics.py         # лічильники
│       ├── runner.py          # обгортка swarm (stateless)
│       └── static/            # index.html · app.js · style.css
└── eval/
    ├── golden.json            # golden set з істиною для recall
    ├── run_eval.py            # recall@k + LLM-Judge → REPORT.md
    └── REPORT.md              # звіт (генерується)
```

Серверний модуль `agrorag_ai` (експорт корпусу + JSON API) живе в репозиторії сайту
як окремий модуль.

---

## Запуск

### 1. Інфраструктура
```bash
docker-compose up -d        # Qdrant :6333, Redis :6379
```

### 2. Залежності та оточення
```bash
copy .env.example .env       # вписати OPENAI_API_KEY, HISTORY_SECRET
pip install -r requirements.txt
```
> На Python 3.14 попередження Pydantic V1 нешкідливе. Якщо якась залежність не
> ставиться — створити venv на Python 3.12.

### 3. Інжест корпусу
Покласти NDJSON (з модуля `agrorag_ai`) у `export/`, тоді:
```bash
python ingestion/ingest.py
```

### 4. Веб-застосунок
```bash
cd app
uvicorn web.main:app --host 0.0.0.0 --port 8000
```
Відкрити **http://localhost:8000/** — чат + вкладка «Метрики».

### 5. CLI (для розробки)
```bash
cd app
python chat.py
```

---

## Безпека (defense-in-depth)

1. **Injection-guard** (`guards.py`) — блокує явні інʼєкції (direct / Base64 / ROT13 /
   reverse), укр. та англ. патерни → 400.
2. **SCOPE-правило** в промптах — модель відмовляє на off-topic та спроби витягти
   модель/інструкції (ловить те, що проскочило повз регулярки, зокрема інші мови).
3. **Підписана історія (HMAC)** — бекенд stateless: клієнт зберігає історію + підпис.
   Підміна попередніх реплік (спроба інʼєкції через контекст) виявляється звіркою HMAC
   → 409 + бан client_id + лічильник `tamper`.

---

## Скріншоти

**Чат: контекст і handoff між агентами.** Діагноз хвороби → контекстне «що мені зараз
робити?» (памʼятає культуру й хворобу) → «які препарати?» → передача агенту «Препарати»
→ підбір із реальними нормами. Праворуч — анімований трейс роботи swarm.

![Чат](screenshots/01-chat-context-handoff.png)

**Дашборд метрик.** Усього запитів, hit-rate кешу, звернення до LLM, токени та оцінка
вартості, блок. інʼєкцій, off-topic відмови, підробка історії, графік у часі, розподіл
по агентах, топ питань.

![Метрики](screenshots/02-metrics-dashboard.png)

**Захист від інʼєкцій та off-topic.** «Забудь інструкції / яку версію використовуєш» —
блок; «яка сьогодні погода?» — ввічлива відмова поза темою.

![Інʼєкції та off-topic](screenshots/03-injection-and-offtopic.png)

**Tamper-захист історії.** Підміна попередньої репліки в `sessionStorage` → сервер
виявляє невідповідність HMAC → 409 «Порушено цілісність історії» + бан.

![Підробка історії](screenshots/04-tamper-blocked.png)

**Eval-пайплайн.** Прогін golden set: deterministic 11/12 (91.7%) → SHIP, recall@5/@10,
LLM-Judge (relevancy / faithfulness).

![Eval](screenshots/05-eval-goldenset.png)

---

## Eval

```bash
cd app
python ../eval/run_eval.py
```
Чотири типи перевірок (за методологією курсу):
- **Deterministic** — наявність очікуваних посилань/змісту, блокування інʼєкцій,
  відмова на off-topic;
- **Retrieval (recall@5 / @10)** — чи правильна нода в топ-k прямого пошуку
  (істина задана вручну в `golden.json`);
- **LLM-as-Judge** — relevancy (чи на те питання) + faithfulness (без вигадок);
- **Категорії** — golden / regression / adversarial.

Результат — у `eval/REPORT.md` з вердиктом SHIP/NO-SHIP. Усі метрики отримані реальним
прогоном.

---

## Технічний стек

- **LLM / ембединги**: OpenAI `gpt-4o` (агенти), `text-embedding-3-large` (3072 dim),
  `gpt-4o-mini` (LLM-суддя в eval)
- **Оркестрація**: LangGraph + langgraph-swarm
- **Векторна БД**: Qdrant (Docker)
- **Кеш / ліміти / метрики**: Redis
- **Веб**: FastAPI + статичний фронт (vanilla JS, без збірки)
- **Джерело даних**: сайт на PHP / MySQL (модуль `agrorag_ai` поверх рідної логіки підбору)
