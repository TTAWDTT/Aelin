from __future__ import annotations

import argparse
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_OUTPUT = REPO_ROOT / "output" / "langgraph-query-smoke"
DEFAULT_API_URL = "http://127.0.0.1:8000"


def _resolve_path(raw: str | None) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _snapshot_tree(root: Path | None) -> dict[str, dict[str, int]]:
    if root is None or not root.exists():
        return {}
    snapshot: dict[str, dict[str, int]] = {}
    for path in root.rglob("*"):
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        snapshot[path.relative_to(root).as_posix()] = {
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }
    return snapshot


def _diff_snapshots(
    before: dict[str, dict[str, int]],
    after: dict[str, dict[str, int]],
) -> dict[str, list[str]]:
    created: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    for path, meta in after.items():
        previous = before.get(path)
        if previous is None:
            created.append(path)
            continue
        if previous != meta:
            modified.append(path)

    for path in before:
        if path not in after:
            deleted.append(path)

    return {
        "created": sorted(created),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
    }


def _iter_sse_events(response: httpx.Response) -> Iterator[dict[str, Any]]:
    event_name = "message"
    event_id = ""
    data_lines: list[str] = []

    def _flush() -> dict[str, Any] | None:
        nonlocal event_name, event_id, data_lines
        if not data_lines:
            event_name = "message"
            event_id = ""
            return None
        payload = {
            "event": event_name or "message",
            "id": event_id or "",
            "data": "\n".join(data_lines),
        }
        event_name = "message"
        event_id = ""
        data_lines = []
        return payload

    for raw_line in response.iter_lines():
        line = str(raw_line or "")
        if not line:
            flushed = _flush()
            if flushed is not None:
                yield flushed
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "id":
            event_id = value
        elif field == "data":
            data_lines.append(value)

    flushed = _flush()
    if flushed is not None:
        yield flushed


def _decode_event_data(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _collect_tool_call_names(value: Any, sink: set[str]) -> None:
    if isinstance(value, dict):
        tool_calls = value.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                name = str(tool_call.get("name") or "").strip()
                if name:
                    sink.add(name)
        for nested in value.values():
            _collect_tool_call_names(nested, sink)
        return
    if isinstance(value, list):
        for item in value:
            _collect_tool_call_names(item, sink)


def _extract_last_ai_message(state: dict[str, Any]) -> dict[str, Any] | None:
    values = state.get("values")
    if not isinstance(values, dict):
        return None
    messages = values.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        msg_type = str(message.get("type") or "").strip().lower()
        if msg_type in {"ai", "assistant"}:
            return message
    return None


def _find_assistant_id(
    client: httpx.Client,
    *,
    api_url: str,
    graph_id: str,
) -> str:
    response = client.post(f"{api_url}/assistants/search", json={})
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError("assistants/search returned unexpected payload")
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("graph_id") or "").strip() == graph_id or str(row.get("name") or "").strip() == graph_id:
            assistant_id = str(row.get("assistant_id") or "").strip()
            if assistant_id:
                return assistant_id
    raise RuntimeError(f'assistant for graph "{graph_id}" not found')


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    api_url = str(args.api_url or DEFAULT_API_URL).rstrip("/")
    output_dir = _resolve_path(args.output_dir) or DEFAULT_OUTPUT
    watch_path = _resolve_path(args.watch_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    thread_id = str(args.thread_id or uuid.uuid4())
    before_snapshot = _snapshot_tree(watch_path)

    with httpx.Client(timeout=httpx.Timeout(args.request_timeout)) as client:
        assistant_id = str(args.assistant_id or "").strip() or _find_assistant_id(
            client,
            api_url=api_url,
            graph_id=args.graph_id,
        )

        create_response = client.post(
            f"{api_url}/threads",
            json={
                "thread_id": thread_id,
                "if_exists": "do_nothing",
            },
        )
        create_response.raise_for_status()

        stream_body = {
            "assistant_id": assistant_id,
            "input": {
                "messages": [
                    {
                        "id": str(uuid.uuid4()),
                        "type": "human",
                        "content": args.prompt,
                    }
                ]
            },
            "context": {
                "workspace": args.workspace,
                "source": args.source,
                "attachment_ids": [],
            },
            "stream_mode": ["messages-tuple", "values", "updates"],
            "stream_subgraphs": True,
            "on_disconnect": "cancel",
            "if_not_exists": "create",
        }

        raw_events: list[dict[str, Any]] = []
        event_counts: Counter[str] = Counter()
        tool_call_names: set[str] = set()

        with client.stream(
            "POST",
            f"{api_url}/threads/{thread_id}/runs/stream",
            json=stream_body,
            headers={"accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            for raw_event in _iter_sse_events(response):
                decoded_data = _decode_event_data(str(raw_event.get("data") or ""))
                event_name = str(raw_event.get("event") or "message")
                event_counts[event_name] += 1
                _collect_tool_call_names(decoded_data, tool_call_names)
                if args.dump_events:
                    raw_events.append(
                        {
                            "event": event_name,
                            "id": str(raw_event.get("id") or ""),
                            "data": decoded_data,
                        }
                    )

        state_response = client.get(
            f"{api_url}/threads/{thread_id}/state",
            params={"subgraphs": "true"},
        )
        state_response.raise_for_status()
        state = state_response.json()

    after_snapshot = _snapshot_tree(watch_path)
    fs_changes = _diff_snapshots(before_snapshot, after_snapshot)
    last_ai_message = _extract_last_ai_message(state if isinstance(state, dict) else {})
    last_ai_content = ""
    if isinstance(last_ai_message, dict):
        last_ai_content = str(last_ai_message.get("content") or "").strip()

    values = state.get("values") if isinstance(state, dict) else {}
    value_keys = sorted(values.keys()) if isinstance(values, dict) else []
    summary = {
        "api_url": api_url,
        "graph_id": args.graph_id,
        "assistant_id": assistant_id,
        "thread_id": thread_id,
        "prompt": args.prompt,
        "workspace": args.workspace,
        "source": args.source,
        "event_counts": dict(event_counts),
        "total_events": int(sum(event_counts.values())),
        "tool_call_names": sorted(tool_call_names),
        "tool_call_count": len(tool_call_names),
        "timed_out": last_ai_content.startswith("模型生成超时"),
        "last_ai_content": last_ai_content,
        "state_value_keys": value_keys,
        "watch_path": str(watch_path) if watch_path is not None else "",
        "fs_changes": fs_changes,
    }
    if args.dump_events:
        summary["events"] = raw_events
    if isinstance(state, dict):
        summary["state"] = state

    output_path = output_dir / f"{thread_id}.json"
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary["output_path"] = str(output_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real LangGraph query smoke test against Aelin.")
    parser.add_argument("--prompt", required=True, help="Prompt to send through /threads/{thread_id}/runs/stream.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--graph-id", default="agent")
    parser.add_argument("--assistant-id", default="")
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--workspace", default="default")
    parser.add_argument("--source", default="chat_ui")
    parser.add_argument("--watch-path", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--request-timeout", type=float, default=180.0)
    parser.add_argument("--dump-events", action="store_true")
    args = parser.parse_args()

    summary = run_smoke(args)
    print(
        json.dumps(
            {
                "thread_id": summary["thread_id"],
                "timed_out": summary["timed_out"],
                "tool_call_names": summary["tool_call_names"],
                "state_value_keys": summary["state_value_keys"],
                "fs_changes": summary["fs_changes"],
                "output_path": summary["output_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
