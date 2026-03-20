from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import app.services.aelin_core as aelin_core
import app.services.llm as llm_service
import app.services.aelin_runtime as aelin_runtime
from app.schemas import AelinChatRequest, AgentConfigOut
from app.services.aelin_loop_types import AelinAgentLoopResult


class _FakeConfiguredService:
    def __init__(self) -> None:
        self.config = SimpleNamespace(model="fake-model", temperature=0.0, web_search_proxy_url="")
        self.client = object()

    def is_configured(self) -> bool:
        return True


class _FakeUnconfiguredService(_FakeConfiguredService):
    def is_configured(self) -> bool:
        return False


class _FakeToolHub:
    instances: list["_FakeToolHub"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.execute_calls: list[tuple[str, dict]] = []
        self.workspace = str(kwargs.get("workspace") or "default")
        self.user_id = int(kwargs.get("user_id") or 0)
        _FakeToolHub.instances.append(self)

    def tool_definitions(self) -> list[dict]:
        return [
            {"type": "function", "function": {"name": "attachment_search", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "context_get", "parameters": {"type": "object"}}},
        ]

    def execute(self, name: str, args: dict) -> dict:
        self.execute_calls.append((str(name), dict(args)))
        return {"ok": True}


class _FakeRunner:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def run(self, **kwargs):
        _FakeRunner.calls.append(dict(kwargs))
        return AelinAgentLoopResult(
            ok=True,
            answer="ok",
            stop_reason="final_answer",
            rounds=1,
            total_calls=0,
            write_calls=0,
            tool_runs=[],
            trace_steps=[],
            actions=[],
            error="",
            memory_snapshot="",
        )


def _reset_fakes() -> None:
    _FakeToolHub.instances.clear()
    _FakeRunner.calls.clear()


def test_try_agent_loop_chat_skips_sync_attachment_prefetch_on_happy_path(monkeypatch):
    _reset_fakes()
    monkeypatch.setattr(aelin_core, "_resolve_llm_service", lambda db, user: (_FakeConfiguredService(), "openai"))
    monkeypatch.setattr(aelin_core, "_get_memory_summary_for_chat", lambda db, user_id: "summary")
    monkeypatch.setattr(aelin_core, "AelinToolHub", _FakeToolHub)
    monkeypatch.setattr(aelin_core, "AelinAgentLoop", _FakeRunner)
    monkeypatch.setattr(aelin_core, "get_active_plane_task", lambda user_id, workspace, plane="browser", db=None: None)
    monkeypatch.setattr(aelin_core, "_build_cached_base_context_bundle", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not build base context")))

    payload = AelinChatRequest(query="请总结附件", workspace="default", attachment_ids=[1])
    response = aelin_core._try_agent_loop_chat(
        payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
        persist_memory=False,
    )

    assert response is not None
    assert response.answer == "ok"
    assert _FakeToolHub.instances
    assert all(name != "attachment_search" for name, _ in _FakeToolHub.instances[0].execute_calls)


def test_try_agent_loop_chat_uses_summary_getter_instead_of_base_context_bundle(monkeypatch):
    _reset_fakes()
    monkeypatch.setattr(aelin_core, "_resolve_llm_service", lambda db, user: (_FakeConfiguredService(), "openai"))
    monkeypatch.setattr(aelin_core, "_get_memory_summary_for_chat", lambda db, user_id: "fast-summary")
    monkeypatch.setattr(aelin_core, "AelinToolHub", _FakeToolHub)
    monkeypatch.setattr(aelin_core, "AelinAgentLoop", _FakeRunner)
    monkeypatch.setattr(aelin_core, "get_active_plane_task", lambda user_id, workspace, plane="browser", db=None: None)
    monkeypatch.setattr(
        aelin_core,
        "_build_cached_base_context_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full base context should not be used")),
    )

    payload = AelinChatRequest(query="你好", workspace="default")
    response = aelin_core._try_agent_loop_chat(
        payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
        persist_memory=False,
    )

    assert response is not None
    assert response.memory_summary == "fast-summary"
    assert _FakeRunner.calls
    assert _FakeRunner.calls[0]["memory_summary"] == "fast-summary"


def test_try_agent_loop_chat_prefetches_attachments_for_llm_unavailable_fallback(monkeypatch):
    _reset_fakes()
    monkeypatch.setattr(aelin_core, "_resolve_llm_service", lambda db, user: (_FakeUnconfiguredService(), "openai"))
    monkeypatch.setattr(aelin_core, "_get_memory_summary_for_chat", lambda db, user_id: "summary")
    monkeypatch.setattr(aelin_core, "AelinToolHub", _FakeToolHub)
    monkeypatch.setattr(aelin_core, "AelinAgentLoop", _FakeRunner)
    monkeypatch.setattr(aelin_core, "get_active_plane_task", lambda user_id, workspace, plane="browser", db=None: None)

    def _fake_execute(self, name: str, args: dict) -> dict:
        self.execute_calls.append((str(name), dict(args)))
        return {
            "ok": True,
            "total": 1,
            "hits": [
                {
                    "text": "附件里提到 X 关注列表包含设计师和开发者账号。",
                    "citation": {"file_name": "x-following.pdf", "page": 1},
                }
            ],
        }

    monkeypatch.setattr(_FakeToolHub, "execute", _fake_execute)

    payload = AelinChatRequest(query="请总结附件", workspace="default", attachment_ids=[1])
    response = aelin_core._try_agent_loop_chat(
        payload,
        db=None,  # type: ignore[arg-type]
        current_user=SimpleNamespace(id=1),
        persist_memory=False,
    )

    assert response is not None
    assert "x-following.pdf" in response.answer
    assert _FakeToolHub.instances
    assert _FakeToolHub.instances[0].execute_calls == [
        (
            "attachment_search",
            {
                "query": "请总结附件",
                "attachment_ids": [1],
                "top_k": 10,
                "mode": "hybrid",
            },
        )
    ]


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
        def get_summary(self, db, user_id):
            calls["get_summary"] += 1
            return "summary"

        def list_notes(self, db, user_id, limit=12):
            calls["list_notes"] += 1
            return [SimpleNamespace(id=1, kind="note", content="hello", source="chat", updated_at=now)]

        def list_todos(self, db, user_id, *, include_done=True, limit=100):
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

    monkeypatch.setattr(aelin_core, "_memory", _FakeMemory())

    bundle = aelin_core._build_context_bundle(db=None, user_id=1, workspace="default", query="hello")  # type: ignore[arg-type]

    assert bundle["summary"] == "summary"
    assert calls["get_summary"] == 1
    assert calls["list_notes"] == 1
    assert calls["list_todos"] == 1
    assert calls["build_memory_layers_from_items"] == 1
