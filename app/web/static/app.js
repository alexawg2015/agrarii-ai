// --- Перемикання вкладок ---
const tabs = document.querySelectorAll(".tab");
const views = document.querySelectorAll(".view");
tabs.forEach(t => t.addEventListener("click", () => {
  tabs.forEach(x => x.classList.remove("active"));
  views.forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  document.getElementById(t.dataset.tab).classList.add("active");
  if (t.dataset.tab === "metrics") loadMetrics();
}));

// --- Чат ---
const messages = document.getElementById("messages");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const traceEl = document.getElementById("trace");
// --- Стан клієнта (історія + підпис зберігаються у вкладці) ---
let clientId = sessionStorage.getItem("agro_cid");
if (!clientId) {
  clientId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));
  sessionStorage.setItem("agro_cid", clientId);
}
let history = JSON.parse(sessionStorage.getItem("agro_hist") || "[]");
let sig = sessionStorage.getItem("agro_sig") || "";

function persistState() {
  sessionStorage.setItem("agro_hist", JSON.stringify(history));
  sessionStorage.setItem("agro_sig", sig || "");
}

function resetConversation() {
  history = [];
  sig = "";
  persistState();
}

function linkify(text) {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>');
}

function addMessage(text, who, cached) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + who;
  const bubble = document.createElement("div");
  bubble.className = "bubble" + (cached ? " cached" : "");
  bubble.innerHTML = linkify(text);
  if (cached) {
    const tag = document.createElement("div");
    tag.className = "tagline";
    tag.textContent = "⚡ відповідь із кешу";
    bubble.appendChild(tag);
  }
  wrap.appendChild(bubble);
  messages.appendChild(wrap);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

function renderTrace(events) {
  traceEl.innerHTML = "";
  events.forEach((ev, i) => {
    const node = document.createElement("div");
    node.className = "tnode " + ev.type;
    let k = "", v = "";
    if (ev.type === "agent") { k = "Агент"; v = ev.name; }
    else if (ev.type === "tool") { k = "Інструмент"; v = ev.name + (ev.args ? `(${ev.args})` : ""); }
    else if (ev.type === "handoff") { k = "Передача"; v = "→ " + ev.to; }
    node.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
    // Поступова поява для ефекту «живої» роботи.
    node.style.animationDelay = (i * 0.06) + "s";
    traceEl.appendChild(node);
  });
}

function setThinking(on) {
  if (on) {
    traceEl.innerHTML = '<div class="tnode agent live"><div class="k">Працюю</div>' +
      '<div class="v dots"><span>.</span><span>.</span><span>.</span></div></div>';
  }
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  addMessage(text, "user");
  input.value = "";
  sendBtn.disabled = true;
  setThinking(true);

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, client_id: clientId, history: history, sig: sig }),
    });
    const data = await resp.json();

    if (resp.status === 403) {
      addMessage("⛔ " + (data.error || "Доступ обмежено."), "bot");
    } else if (resp.status === 409 || data.reset) {
      addMessage("🔐 " + (data.error || "Порушено цілісність історії. Почнімо заново."), "bot");
      resetConversation();
      traceEl.innerHTML = '<div class="tnode handoff"><div class="k">Безпека</div><div class="v">tamper: історію скинуто</div></div>';
    } else if (resp.status === 429) {
      addMessage(`⏳ ${data.error} (через ${data.retry_after} с)`, "bot");
    } else if (data.blocked) {
      addMessage("🛡️ " + data.answer, "bot");
      traceEl.innerHTML = '<div class="tnode handoff"><div class="k">Захист</div><div class="v">Заблоковано: ' + data.reason + '</div></div>';
      // інʼєкція теж стає частиною підписаної історії
      if (data.sig !== undefined) { history.push({ role: "user", content: text }); history.push({ role: "assistant", content: data.answer }); sig = data.sig; persistState(); }
    } else if (data.error) {
      addMessage("⚠️ " + data.error, "bot");
    } else {
      addMessage(data.answer || "(порожня відповідь)", "bot", data.cached);
      if (data.trace && data.trace.length) renderTrace(data.trace);
      else if (data.cached) traceEl.innerHTML = '<div class="tnode agent"><div class="k">Кеш</div><div class="v">⚡ score ' + (data.score ?? "") + '</div></div>';
      // оновлюємо історію та підпис
      history.push({ role: "user", content: text });
      history.push({ role: "assistant", content: data.answer || "" });
      sig = data.sig || sig;
      persistState();
    }
  } catch (e) {
    addMessage("⚠️ Помилка зʼєднання: " + e, "bot");
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

sendBtn.addEventListener("click", send);
input.addEventListener("keydown", e => { if (e.key === "Enter") send(); });

// --- Метрики ---
const cardDefs = [
  { key: "requests_total", lbl: "Усього запитів" },
  { key: "cache_hit", lbl: "Влучань у кеш" },
  { key: "cache_hit_rate", lbl: "Hit rate, %" },
  { key: "llm_calls", lbl: "Звернень до LLM" },
  { key: "tokens_in", lbl: "Токени (вхід)" },
  { key: "tokens_out", lbl: "Токени (вихід)" },
  { key: "cost_usd", lbl: "Оцінка вартості, $" },
  { key: "avg_latency_ms", lbl: "Сер. латентність, мс" },
  { key: "blocked_injection", lbl: "Блок. інʼєкцій (guard)", warn: true },
  { key: "refused_scope", lbl: "Off-topic відмов", warn: true },
  { key: "tamper", lbl: "Підробка історії", warn: true },
  { key: "rate_limited", lbl: "Rate-limited (429)", warn: true },
];

const AGENT_COLORS = { "Хвороби": "#46d18a", "Шкідники": "#d9a441", "Препарати": "#4aa3e0" };

function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

async function loadMetrics() {
  try {
    const m = await (await fetch("/api/metrics")).json();

    // картки
    const cards = document.getElementById("cards");
    cards.innerHTML = "";
    cardDefs.forEach(d => {
      const c = document.createElement("div");
      c.className = "card" + (d.warn && m[d.key] > 0 ? " warn" : "");
      c.innerHTML = `<div class="num">${m[d.key] ?? 0}</div><div class="lbl">${d.lbl}</div>`;
      cards.appendChild(c);
    });

    // кеш-бари
    const total = (m.cache_hit || 0) + (m.cache_miss || 0) || 1;
    document.getElementById("bar-hit").style.width = (100 * (m.cache_hit || 0) / total) + "%";
    document.getElementById("bar-miss").style.width = (100 * (m.cache_miss || 0) / total) + "%";
    document.getElementById("hit-val").textContent = m.cache_hit || 0;
    document.getElementById("miss-val").textContent = m.cache_miss || 0;

    // часовий ряд
    const spark = document.getElementById("spark");
    const ts = m.timeseries || [];
    const max = Math.max(1, ...ts);
    spark.innerHTML = ts.map(v =>
      `<div class="sbar" style="height:${Math.round(100 * v / max)}%" title="${v}"></div>`
    ).join("");

    // агенти
    const agents = m.agents || {};
    const aTotal = Object.values(agents).reduce((a, b) => a + b, 0) || 1;
    document.getElementById("agents").innerHTML = Object.keys(agents).length
      ? Object.entries(agents).map(([name, n]) =>
          `<div class="bar"><span class="bar-label">${esc(name)}</span>
           <div class="track"><div class="fill" style="width:${100 * n / aTotal}%;background:${AGENT_COLORS[name] || '#888'}"></div></div>
           <span>${n}</span></div>`).join("")
      : '<div class="empty">ще немає даних</div>';

    // топ питань
    const top = m.top_questions || [];
    document.getElementById("top").innerHTML = top.length
      ? top.map(t => `<div class="row"><span>${esc(t.q)}</span><b>${t.n}</b></div>`).join("")
      : '<div class="empty">ще немає даних</div>';

    // останні діалоги
    const recent = m.recent || [];
    document.getElementById("recent").innerHTML = recent.length
      ? recent.map(r => `
        <div class="dlg">
          <div class="dlg-q">❓ ${esc(r.q)}
            ${r.cached ? '<span class="pill cache">кеш</span>' : `<span class="pill">${r.latency_ms} мс</span>`}
            ${(r.agents || []).map(a => `<span class="pill agent">${esc(a)}</span>`).join("")}
          </div>
          <div class="dlg-a">${esc(r.a)}…</div>
        </div>`).join("")
      : '<div class="empty">ще немає даних</div>';
  } catch (e) {
    console.error(e);
  }
}

document.getElementById("refresh").addEventListener("click", loadMetrics);
document.getElementById("reset").addEventListener("click", async () => {
  await fetch("/api/metrics/reset", { method: "POST" });
  loadMetrics();
});
