"""Обгортка swarm для веб-шару (STATELESS).

Приймає повну історію (від клієнта, перевірену HMAC) + нове повідомлення,
проганяє граф і повертає фінальну відповідь + трейс + токени + агентів.
Памʼять не зберігаємо на сервері — джерело правди історії на клієнті.
"""

from langchain_core.messages import AIMessage

from agents.swarm import AGENT_LABELS, build_swarm

_agent = None

_ROLE = {"user": "human", "human": "human", "assistant": "ai", "ai": "ai", "system": "system"}


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_swarm(use_memory=False)  # stateless
    return _agent


def run_chat(history, message):
    """history — список {'role','content'}; message — нове повідомлення користувача."""
    agent = get_agent()

    msgs = [(_ROLE.get(h.get("role", "user"), "human"), h.get("content", "")) for h in (history or [])]
    msgs.append(("human", message))

    trace = []
    answer = ""
    last_agent = None
    tokens_in = 0
    tokens_out = 0
    agents_involved = []

    for chunk in agent.stream({"messages": msgs}, stream_mode="updates"):
        for node, update in chunk.items():
            label = AGENT_LABELS.get(node, node)
            if node != last_agent:
                last_agent = node
                trace.append({"type": "agent", "name": label})
            if node in AGENT_LABELS and label not in agents_involved:
                agents_involved.append(label)
            for m in update.get("messages", []):
                if not isinstance(m, AIMessage):
                    continue
                usage = getattr(m, "usage_metadata", None)
                if usage:
                    tokens_in += usage.get("input_tokens", 0) or 0
                    tokens_out += usage.get("output_tokens", 0) or 0
                for call in (m.tool_calls or []):
                    name = call.get("name", "")
                    if name.startswith("transfer_to_"):
                        target = name.replace("transfer_to_", "")
                        trace.append({"type": "handoff", "to": AGENT_LABELS.get(target, target)})
                    else:
                        args = call.get("args", {})
                        shown = args.get("query") or ", ".join(f"{k}={v}" for k, v in args.items() if v)
                        trace.append({"type": "tool", "name": name, "args": shown})
                if m.content:
                    answer = m.content

    return {
        "answer": answer, "trace": trace,
        "tokens_in": tokens_in, "tokens_out": tokens_out, "agents": agents_involved,
    }
