from app.schemas import ChatRequest


def test_aelin_chat_request_deduplicates_attachment_ids():
    payload = ChatRequest(query="总结", attachment_ids=[5, 5, "10", -1, 0, "x"])  # type: ignore[list-item]
    assert payload.attachment_ids == [5, 10]


def test_aelin_chat_request_attachment_only_query_fallback():
    payload = ChatRequest(query="", attachment_ids=[3, 3])
    assert payload.attachment_ids == [3]
    assert payload.query == "请先基于我上传的附件内容给出结论和建议。"
