from __future__ import annotations

from app.services.skill_loader import (
    get_skill_bodies_for_query_and_tools,
    get_skill_prompt_by_slug,
    get_skill_prompts_for_query_and_tools,
    list_skill_catalog_for_query_and_tools,
    render_skill_catalog_prompt,
)


def test_skill_loader_injects_crawl4ai_skill_for_matching_query():
    bodies = get_skill_bodies_for_query_and_tools(
        "帮我抓取这个文档站并转成 markdown 后总结",
        ["crawl4ai_fetch", "web_search"],
    )

    assert bodies
    combined = "\n".join(bodies)
    assert "Crawl4AI" in combined
    assert "markdown" in combined.lower()


def test_skill_loader_skips_crawl4ai_when_query_does_not_match_triggers():
    bodies = get_skill_bodies_for_query_and_tools(
        "你好，今天天气怎么样",
        ["crawl4ai_fetch"],
    )

    assert bodies == []


def test_skill_loader_formats_prompt_with_metadata_header():
    prompts = get_skill_prompts_for_query_and_tools(
        "帮我抓取这个文档站并转成 markdown 后总结",
        ["crawl4ai_fetch"],
    )

    assert prompts
    prompt = prompts[0]
    assert "[AELIN SKILL]" in prompt
    assert "slug=crawl4ai" in prompt
    assert "applies_to_tools=crawl4ai_fetch" in prompt


def test_skill_loader_injects_google_skill_for_workspace_queries():
    prompts = get_skill_prompts_for_query_and_tools(
        "帮我看看 Gmail 未读邮件，再找一下 Drive 里的 roadmap",
        ["google_status", "google_gmail_list", "google_drive_search"],
    )

    assert prompts
    prompt = "\n".join(prompts)
    assert "Google Workspace" in prompt
    assert "google_gmail_list" in prompt
    assert "google_drive_search" in prompt


def test_skill_loader_injects_pinchtab_plane_skill_for_browser_plane_queries():
    prompts = get_skill_prompts_for_query_and_tools(
        "帮我总结我的 X 关注列表，并在登录后继续处理",
        ["plane", "web_search"],
    )

    assert prompts
    prompt = "\n".join(prompts)
    assert "PinchTab" in prompt
    assert "browser plane" in prompt.lower()


def test_skill_loader_builds_catalog_prompt_and_can_read_by_slug():
    entries = list_skill_catalog_for_query_and_tools(
        "帮我总结我的 X 关注列表，并在登录后继续处理",
        ["plane", "skill"],
    )

    assert entries
    pinchtab = next(item for item in entries if item.get("slug") == "pinchtab")
    assert "summary" in pinchtab
    catalog_prompt = render_skill_catalog_prompt(
        "帮我总结我的 X 关注列表，并在登录后继续处理",
        ["plane", "skill"],
    )
    assert "[AELIN SKILL CATALOG]" in catalog_prompt
    assert "pinchtab" in catalog_prompt

    prompt = get_skill_prompt_by_slug("pinchtab")
    assert "[AELIN SKILL]" in prompt
    assert "slug=pinchtab" in prompt
