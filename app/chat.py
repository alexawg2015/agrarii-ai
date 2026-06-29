"""CLI-чат зі swarm-асистентом (Хвороби · Шкідники · Препарати) з трейсом.

Запуск (з кореня проєкту; Qdrant піднятий, корпус проінжещено, сайт із API доступний):
    python app/chat.py
"""

from langchain_core.messages import AIMessage

from agents.swarm import AGENT_LABELS, build_swarm


def main():
    agent = build_swarm()
    cfg = {"configurable": {"thread_id": "cli"}}

    print("Агро-асистент (swarm). Опиши проблему або постав питання. Порожній рядок — вихід.\n")
    active = None
    while True:
        try:
            text = input("Ви: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            break

        for chunk in agent.stream({"messages": [("user", text)]}, cfg, stream_mode="updates"):
            for node, update in chunk.items():
                if node != active:
                    active = node
                    print(f"  [агент: {AGENT_LABELS.get(node, node)}]")
                for message in update.get("messages", []):
                    if not isinstance(message, AIMessage):
                        continue
                    for call in (message.tool_calls or []):
                        name = call.get("name", "")
                        args = call.get("args", {})
                        if name.startswith("transfer_to_"):
                            target = name.replace("transfer_to_", "")
                            print(f"  ↪ передача: {AGENT_LABELS.get(target, target)}")
                        else:
                            shown = args.get("query") or ", ".join(f"{k}={v}" for k, v in args.items() if v)
                            print(f"  🔧 {name}({shown})")
                    if message.content:
                        print(f"\nАгент: {message.content}\n")


if __name__ == "__main__":
    main()
