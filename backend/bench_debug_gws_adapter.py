from __future__ import annotations

from app.services.aelin_agent_loop import _adapt_text_tool_call


def main() -> None:
    text = (
        "我来帮你创建一个关于Agent Swarm的Google云文档。"
        "<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>google_workspace"
        "<｜tool▁sep｜>{\"action\": \"docs_create\", \"docs_title\": \"Agent Swarm 技术详解\", \"docs_content\": \"# Agent Swarm 概述\"}"
    )
    result = _adapt_text_tool_call(text)
    print("ADAPT_RESULT:", result)


if __name__ == "__main__":
    main()

