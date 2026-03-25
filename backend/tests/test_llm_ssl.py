from __future__ import annotations

import ssl

from app.schemas import AgentConfigOut
from app.services.foundation import llm as llm_module
from app.services.foundation.llm import LLMService
from app.services.deepagents import deepagents_graph as dag


def test_llm_service_uses_configured_http_client(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)

    monkeypatch.setattr(llm_module.openai, "Client", _FakeClient)
    service = LLMService(
        AgentConfigOut(
            provider="openai",
            base_url="https://example.com/v1",
            model="test-model",
            temperature=0.2,
            verify_ssl=False,
            has_api_key=True,
            web_search_proxy_url="",
        ),
        api_key="test-key",
    )

    assert service.client is not None
    http_client = captured.get("http_client")
    assert http_client is not None
    assert http_client.follow_redirects is True
    assert http_client._transport._pool._ssl_context.verify_mode == ssl.CERT_NONE
    assert http_client._transport._pool._ssl_context.check_hostname is False


def test_deepagents_chat_model_reuses_llm_http_client(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)

    monkeypatch.setattr(dag, "ChatOpenAI", _FakeChatOpenAI)
    service = LLMService(
        AgentConfigOut(
            provider="openai",
            base_url="https://example.com/v1",
            model="test-model",
            temperature=0.2,
            verify_ssl=False,
            has_api_key=True,
            web_search_proxy_url="",
        ),
        api_key="test-key",
    )

    model = dag._build_chat_model(service, "openai")

    assert model is not None
    http_client = captured.get("http_client")
    assert http_client is not None
    assert http_client.follow_redirects is True
    assert http_client._transport._pool._ssl_context.verify_mode == ssl.CERT_NONE
    assert http_client._transport._pool._ssl_context.check_hostname is False
