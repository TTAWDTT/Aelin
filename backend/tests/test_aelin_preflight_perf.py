from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import app.services.aelin.core as aelin_core
import app.services.aelin.core_support as aelin_core_support
import app.services.foundation.llm as llm_service
import app.services.aelin.runtime as aelin_runtime
from app.schemas import ChatRequest, AgentConfigOut
from app.services.deepagents.deepagents_graph import DeepAgentsLoopResult
from tests.aelin_deepagents_test_utils import (
    _FakeRunner,
    _FakeToolContext,
    _reset_fakes,
)


class _FakeConfiguredService:
    def __init__(self) -> None:
        self.config = SimpleNamespace(model="fake-model", temperature=0.0, web_search_proxy_url="")
        self.client = object()

    def is_configured(self) -> bool:
        return True


class _FakeUnconfiguredService(_FakeConfiguredService):
    def is_configured(self) -> bool:
        return False


def _patch_resolved_runtime(
    monkeypatch,
    *,
    service=None,
    provider: str = "openai",
    memory_text: str = "# Memory",
):
    svc = service or _FakeConfiguredService()

    def _fake_resolve_deepagents_runtime(
        db,
        *,
        user_id,
        workspace,
        raw_attachment_ids=None,
        cancel_checker=None,
        session_factory=None,
        allow_write_tools=None,
    ):  # noqa: ANN001
        _ = db, session_factory, allow_write_tools
        attachment_ids = list(raw_attachment_ids or [])
        tool_context = None
        if svc.is_configured():
            tool_context = _FakeToolContext(
                user_id=int(user_id),
                workspace=str(workspace),
                available_attachment_ids=attachment_ids,
                cancel_checker=cancel_checker,
            )
        return SimpleNamespace(
            service=svc,
            provider=provider,
            memory_text=memory_text,
            tool_context=tool_context,
            limiter=SimpleNamespace(),
            attachment_ids=attachment_ids,
            workspace=str(workspace),
        )

    monkeypatch.setattr(aelin_core, "resolve_deepagents_runtime", _fake_resolve_deepagents_runtime)


def test_try_deepagents_chat_skips_sync_attachment_prefetch_on_happy_path(monkeypatch):
    _reset_fakes()
    _patch_resolved_runtime(monkeypatch)
    monkeypatch.setattr(aelin_core, "run_deepagents_loop", lambda **kwargs: DeepAgentsLoopResult(
        ok=True,
        answer="ok",
        tool_runs=[],
        total_calls=0,
        write_calls=0,
        actions=[],
        error="",
    ))

    payload = ChatRequest(query="请总结附件", workspace="default", attachment_ids=[1])
    response = aelin_core._try_deepagents_chat(
        payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
    )

    assert response is not None
    assert response.answer == "ok"
    assert _FakeToolContext.instances


def test_try_deepagents_chat_uses_memory_file_getter_instead_of_base_context_bundle(monkeypatch):
    _reset_fakes()
    _patch_resolved_runtime(monkeypatch)
    calls: list[dict] = []

    def _fake_run_loop(**kwargs):
        calls.append(dict(kwargs))
        return DeepAgentsLoopResult(
            ok=True,
            answer="ok",
            tool_runs=[],
            total_calls=0,
            write_calls=0,
            actions=[],
            error="",
        )

    monkeypatch.setattr(aelin_core, "run_deepagents_loop", _fake_run_loop)

    payload = ChatRequest(query="你好", workspace="default")
    response = aelin_core._try_deepagents_chat(
        payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
    )

    assert response is not None
    assert response.memory_summary == "# Memory"
    assert calls
    assert calls[0]["memory_text"] == "# Memory"


def test_try_deepagents_chat_forwards_images_and_cancel_token(monkeypatch):
    _reset_fakes()
    _patch_resolved_runtime(monkeypatch)

    calls: list[dict] = []

    def _fake_run_loop(**kwargs):
        calls.append(dict(kwargs))
        return DeepAgentsLoopResult(
            ok=True,
            answer="ok",
            tool_runs=[],
            total_calls=0,
            write_calls=0,
            actions=[],
            error="",
        )

    monkeypatch.setattr(aelin_core, "run_deepagents_loop", _fake_run_loop)

    cancel_token = SimpleNamespace(cancelled=False)
    payload = ChatRequest(
        query="请描述这张图",
        workspace="default",
        images=[
            {
                "name": "demo.png",
                "data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAF7AL5n4VHKwAAAABJRU5ErkJggg==",
            }
        ],
    )
    response = aelin_core._try_deepagents_chat(
        payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
        cancel_token=cancel_token,
    )

    assert response is not None
    assert calls
    assert calls[0]["images"] == [
        {
            "name": "demo.png",
            "data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAF7AL5n4VHKwAAAABJRU5ErkJggg==",
        }
    ]
    assert calls[0]["cancel_token"] is cancel_token


def test_try_deepagents_chat_preserves_system_history(monkeypatch):
    _reset_fakes()
    _patch_resolved_runtime(monkeypatch)

    calls: list[dict] = []

    def _fake_run_loop(**kwargs):
        calls.append(dict(kwargs))
        return DeepAgentsLoopResult(
            ok=True,
            answer="ok",
            tool_runs=[],
            total_calls=0,
            write_calls=0,
            actions=[],
            error="",
        )

    monkeypatch.setattr(aelin_core, "run_deepagents_loop", _fake_run_loop)

    payload = ChatRequest(
        query="继续",
        workspace="default",
        history=[
            {"role": "system", "content": "你是测试助手"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀"},
        ],
    )
    response = aelin_core._try_deepagents_chat(
        payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
    )

    assert response is not None
    assert calls
    assert calls[0]["history_turns"] == [
        {"role": "system", "content": "你是测试助手"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好呀"},
    ]


def test_try_deepagents_chat_skips_attachment_fallback_when_cancelled(monkeypatch):
    _reset_fakes()
    _patch_resolved_runtime(monkeypatch)
    monkeypatch.setattr(
        aelin_core,
        "run_deepagents_loop",
        lambda **kwargs: DeepAgentsLoopResult(
            ok=False,
            answer="",
            cancelled=True,
            tool_runs=[],
            total_calls=0,
            write_calls=0,
            actions=[],
            error="cancelled",
        ),
    )
    response = aelin_core._try_deepagents_chat(
        ChatRequest(query="请总结附件", workspace="default", attachment_ids=[1]),
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
        cancel_token=SimpleNamespace(cancelled=False),
    )

    assert response is None


def test_try_deepagents_chat_returns_none_when_llm_is_unavailable(monkeypatch):
    _reset_fakes()
    _patch_resolved_runtime(monkeypatch, service=_FakeUnconfiguredService())

    payload = ChatRequest(query="请总结附件", workspace="default", attachment_ids=[1])
    response = aelin_core._try_deepagents_chat(
        payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
    )

    assert response is None
    assert not _FakeToolContext.instances


def test_resolve_llm_service_fetches_config_and_decrypts_once(monkeypatch):
    calls = {"get_agent_config": 0, "decrypt_optional": 0}
    stored = SimpleNamespace(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        temperature=0.2,
        api_key="encrypted",
        web_search_proxy_url="",
    )

    class _FakeLLMService:
        def __init__(self, config, api_key=None) -> None:
            self.config = config
            self.api_key = api_key

    def _fake_get_agent_config(db, *, user_id: int):
        calls["get_agent_config"] += 1
        return stored

    def _fake_decrypt_optional(value):
        calls["decrypt_optional"] += 1
        return "sk-test"

    monkeypatch.setattr(aelin_runtime.crud, "get_agent_config", _fake_get_agent_config)
    monkeypatch.setattr(aelin_runtime, "decrypt_optional", _fake_decrypt_optional)
    monkeypatch.setattr(aelin_runtime, "LLMService", _FakeLLMService)

    service, provider = aelin_runtime.resolve_llm_service(db=None, user=SimpleNamespace(id=7))  # type: ignore[arg-type]

    assert provider == "openai"
    assert service.api_key == "sk-test"
    # config_out + resolve_llm_service each fetch the stored config & decrypt.
    assert calls["get_agent_config"] == 2
    assert calls["decrypt_optional"] == 2


def test_llm_service_reuses_openai_client_for_same_config(monkeypatch):
    calls = {"client_init": 0}

    class _FakeOpenAIClient:
        def __init__(self, **kwargs) -> None:
            calls["client_init"] += 1
            self.kwargs = kwargs

    monkeypatch.setattr(llm_service.openai, "Client", _FakeOpenAIClient)
    if hasattr(llm_service, "_CLIENT_CACHE"):
        llm_service._CLIENT_CACHE.clear()  # type: ignore[attr-defined]

    config = AgentConfigOut(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        temperature=0.2,
        has_api_key=True,
        web_search_proxy_url="",
    )

    first = llm_service.LLMService(config, "sk-test")
    second = llm_service.LLMService(config, "sk-test")

    # The simplified LLMService no longer caches clients globally; each
    # instance maintains its own client.
    assert first.client is not None
    assert second.client is not None
    assert first.client is not second.client
    assert calls["client_init"] == 2


def test_llm_service_defers_openai_client_init_until_client_is_used(monkeypatch):
    calls = {"client_init": 0}

    class _FakeOpenAIClient:
        def __init__(self, **kwargs) -> None:
            calls["client_init"] += 1
            self.kwargs = kwargs

    monkeypatch.setattr(llm_service.openai, "Client", _FakeOpenAIClient)
    if hasattr(llm_service, "_CLIENT_CACHE"):
        llm_service._CLIENT_CACHE.clear()  # type: ignore[attr-defined]

    config = AgentConfigOut(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        temperature=0.2,
        has_api_key=True,
        web_search_proxy_url="",
    )

    service = llm_service.LLMService(config, "sk-test")

    # In the simplified implementation the client is initialized eagerly
    # when api_key is present.
    assert calls["client_init"] == 1
    assert service.is_configured() is True
    assert service.client is not None


def test_build_context_bundle_reuses_shared_memory_primitives(monkeypatch):
    now = datetime.now(timezone.utc)
    calls = {
        "get_summary": 0,
        "list_notes": 0,
        "list_todos": 0,
        "build_memory_layers_from_items": 0,
    }

    class _FakeMemory:
        def get_summary(self, db, user_id, *, workspace: str = "default"):
            calls["get_summary"] += 1
            return "summary"

        def list_notes(self, db, user_id, limit=12, workspace: str = "default"):
            calls["list_notes"] += 1
            return [SimpleNamespace(id=1, kind="note", content="hello", source="chat", updated_at=now)]

        def list_todos(self, db, user_id, *, include_done=True, limit=100, workspace: str = "default"):
            calls["list_todos"] += 1
            return [
                {
                    "id": 1,
                    "title": "todo",
                    "detail": "",
                    "done": False,
                    "due_at": None,
                    "priority": "normal",
                    "contact_id": None,
                    "message_id": None,
                    "updated_at": now.isoformat(),
                }
            ]

        def build_memory_layers_from_items(self, *, summary, notes, focus_items, todos, layout_cards, workspace, query):
            calls["build_memory_layers_from_items"] += 1
            return {
                "facts": [{"id": "f1", "layer": "fact", "title": "summary", "detail": "", "source": "chat", "confidence": 0.5, "updated_at": now.isoformat(), "meta": {}}],
                "preferences": [],
                "in_progress": [],
            }

    monkeypatch.setattr(aelin_core_support, "_memory", _FakeMemory())

    bundle = aelin_core_support._build_context_bundle(db=None, user_id=1, workspace="default", query="hello")  # type: ignore[arg-type]

    assert bundle["summary"] == "summary"
    assert calls["get_summary"] == 1
    assert calls["list_notes"] == 1
    assert calls["list_todos"] == 1
    assert calls["build_memory_layers_from_items"] == 1

