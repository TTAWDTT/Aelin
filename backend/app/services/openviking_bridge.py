from __future__ import annotations

import importlib
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.settings import settings
from app.services.openviking_utils import (
    _TOKEN_RE,
    _iso,
    _normalize_workspace,
    _safe_json,
    _sha1,
    _slug,
    _utcnow,
    DiaryTreeNode,
    FileMemoryHit,
)

_LOG = logging.getLogger(__name__)


class TrackingFileMemoryBridge:
    """
    File-first memory projection for tracking targets.

    - Writes profile/snapshot/change timeline as markdown.
    - Retrieval uses optional OpenViking SDK; falls back to local lexical scoring.
    """

    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "openviking_enabled", True))
        self.query_limit = max(1, min(32, int(getattr(settings, "openviking_query_limit", 8))))
        configured_root = str(getattr(settings, "openviking_data_dir", "../data/aelin_memory")).strip() or "../data/aelin_memory"
        root_path = Path(configured_root)
        if not root_path.is_absolute():
            backend_dir = Path(__file__).resolve().parents[2]
            root_path = (backend_dir / root_path).resolve()
        self.root = root_path
        self.root.mkdir(parents=True, exist_ok=True)
        self._io_lock = threading.Lock()
        self._openviking = self._load_openviking()
        self._local_cache_lock = threading.Lock()
        self._local_cache_max_entries = max(
            200,
            min(20000, int(getattr(settings, "openviking_local_cache_max_entries", 2000) or 2000)),
        )
        self._local_doc_cache: dict[str, dict[str, Any]] = {}

    def _load_openviking(self) -> Any | None:
        if not self.enabled:
            return None
        try:
            module = importlib.import_module("openviking")
        except Exception:
            return None
        client_cls = getattr(module, "OpenViking", None) or getattr(module, "Client", None)
        if client_cls is None:
            return None
        try:
            return client_cls(root_dir=str(self.root))
        except TypeError:
            try:
                return client_cls(str(self.root))
            except Exception:
                return None
        except Exception:
            return None

    def _target_meta(self, target: Any) -> dict[str, str]:
        user_id = int(getattr(target, "user_id", 0) or 0)
        workspace = _normalize_workspace(str(getattr(target, "workspace", "default") or "default"))
        source_type = str(getattr(target, "source_type", "web") or "web").strip().lower() or "web"
        track_type = str(getattr(target, "track_type", "term") or "term").strip().lower() or "term"
        source_key = str(getattr(target, "source_key", "") or "").strip()
        display_name = str(getattr(target, "display_name", source_key) or source_key).strip() or source_key
        canonical_seed = f"{user_id}:{workspace}:{track_type}:{source_key}".lower()
        canonical_id = _sha1(canonical_seed)
        target_hash = _sha1(f"{source_type}:{source_key}".lower())[:16]
        return {
            "user_id": str(user_id),
            "workspace": workspace,
            "source_type": source_type,
            "track_type": track_type,
            "source_key": source_key,
            "display_name": display_name,
            "canonical_id": canonical_id,
            "target_hash": target_hash,
        }

    def _target_dir(self, target: Any) -> Path:
        meta = self._target_meta(target)
        return (
            self.root
            / "users"
            / meta["user_id"]
            / "workspaces"
            / _slug(meta["workspace"], fallback="default")
            / "tracking"
            / _slug(meta["source_type"], fallback="web")
            / meta["target_hash"]
        )

    def _workspace_root(self, *, user_id: int, workspace: str) -> Path:
        return (
            self.root
            / "users"
            / str(max(0, int(user_id)))
            / "workspaces"
            / _slug(_normalize_workspace(workspace), fallback="default")
        )

    def _tracking_root(self, *, user_id: int, workspace: str) -> Path:
        return self._workspace_root(user_id=user_id, workspace=workspace) / "tracking"

    def _diary_root(self, *, user_id: int, workspace: str) -> Path:
        return self._workspace_root(user_id=user_id, workspace=workspace) / "diary"

    def _normalize_topic_path(self, topic_path: list[str] | None, *, fallback: str = "综合") -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        source = topic_path if isinstance(topic_path, list) else []
        for item in source:
            text = str(item or "").strip()
            if not text:
                continue
            text = text[:64]
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= 6:
                break
        if not out:
            out.append(fallback[:32] or "综合")
        return out

    def _candidate_search_dirs(
        self,
        *,
        user_id: int,
        workspace: str,
        source: str | None,
    ) -> list[Path]:
        tracking_root = self._tracking_root(user_id=user_id, workspace=workspace)
        diary_root = self._diary_root(user_id=user_id, workspace=workspace)
        out: list[Path] = []
        source_norm = str(source or "").strip().lower()
        if source_norm:
            out.append(tracking_root / _slug(source_norm, fallback="web"))
        else:
            out.append(tracking_root)
        out.append(diary_root)
        return out

    def _write_markdown(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with self._io_lock:
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(path)

    def sync_target_profile(self, target: Any) -> None:
        if not self.enabled:
            return
        try:
            meta = self._target_meta(target)
            config_json = str(getattr(target, "config_json", "") or "")
            description = str(getattr(target, "description", "") or "")
            status = str(getattr(target, "status", "active") or "active")
            tags_json = str(getattr(target, "tags_json", "[]") or "[]")
            body = [
                "# Tracking Profile",
                "",
                f"- canonical_id: `{meta['canonical_id']}`",
                f"- target_hash: `{meta['target_hash']}`",
                f"- display_name: {meta['display_name']}",
                f"- source_type: {meta['source_type']}",
                f"- track_type: {meta['track_type']}",
                f"- workspace: {meta['workspace']}",
                f"- status: {status}",
                f"- updated_at: {_iso(_utcnow())}",
                "",
                "## Description",
                "",
                description or "(empty)",
                "",
                "## Tags",
                "",
                "```json",
                tags_json if tags_json.strip() else "[]",
                "```",
                "",
                "## Config",
                "",
                "```json",
                config_json if config_json.strip() else "{}",
                "```",
                "",
            ]
            out_path = self._target_dir(target) / "profile.md"
            self._write_markdown(out_path, "\n".join(body))
        except Exception as exc:
            _LOG.warning("file-memory profile sync failed: %s", exc)

    def append_snapshot(self, *, target: Any, snapshot: Any, normalized_payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            meta = self._target_meta(target)
            ts = _iso(getattr(snapshot, "fetched_at", None) or _utcnow()) or _iso(_utcnow())
            ts_id = _slug(ts.replace(":", "").replace("+00:00", "Z"), fallback="t", max_len=48)
            version = int(getattr(snapshot, "version_no", 0) or 0)
            fetch_status = str(getattr(snapshot, "fetch_status", "ok") or "ok")
            fetch_error = str(getattr(snapshot, "fetch_error", "") or "")
            normalized = normalized_payload if isinstance(normalized_payload, dict) else {}
            item_count = len(normalized.get("items") or []) if isinstance(normalized.get("items"), list) else 0
            body = [
                "# Tracking Snapshot",
                "",
                f"- canonical_id: `{meta['canonical_id']}`",
                f"- target: {meta['display_name']}",
                f"- source: {meta['source_type']}",
                f"- kind: snapshot",
                f"- version: {version}",
                f"- fetch_status: {fetch_status}",
                f"- fetched_at: {ts}",
                f"- item_count: {item_count}",
            ]
            if fetch_error:
                body.append(f"- fetch_error: {fetch_error[:500]}")
            body.extend(
                [
                    "",
                    "## Normalized Payload",
                    "",
                    "```json",
                    _safe_json(normalized),
                    "```",
                    "",
                ]
            )
            out_path = self._target_dir(target) / "snapshots" / f"{ts_id}_v{max(0, version)}_{_slug(fetch_status, fallback='ok', max_len=18)}.md"
            self._write_markdown(out_path, "\n".join(body))
        except Exception as exc:
            _LOG.warning("file-memory snapshot append failed: %s", exc)

    def append_change(self, *, target: Any, change: Any, diff_payload: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        try:
            meta = self._target_meta(target)
            ts = _iso(getattr(change, "created_at", None) or _utcnow()) or _iso(_utcnow())
            ts_id = _slug(ts.replace(":", "").replace("+00:00", "Z"), fallback="t", max_len=48)
            change_type = str(getattr(change, "change_type", "updated_item") or "updated_item")
            severity = str(getattr(change, "severity", "medium") or "medium")
            title = str(getattr(change, "title", "") or "").strip()
            summary = str(getattr(change, "summary", "") or "").strip()
            payload = diff_payload if isinstance(diff_payload, dict) else {}
            body = [
                "# Tracking Change",
                "",
                f"- canonical_id: `{meta['canonical_id']}`",
                f"- target: {meta['display_name']}",
                f"- source: {meta['source_type']}",
                f"- kind: change",
                f"- change_type: {change_type}",
                f"- severity: {severity}",
                f"- created_at: {ts}",
                "",
                "## Title",
                "",
                title or "(empty)",
                "",
                "## Summary",
                "",
                summary or "(empty)",
                "",
                "## Diff",
                "",
                "```json",
                _safe_json(payload),
                "```",
                "",
            ]
            out_path = self._target_dir(target) / "timeline" / f"{ts_id}_{_slug(change_type, fallback='change', max_len=24)}_{int(getattr(change, 'id', 0) or 0)}.md"
            self._write_markdown(out_path, "\n".join(body))
        except Exception as exc:
            _LOG.warning("file-memory change append failed: %s", exc)

    def append_insight(
        self,
        *,
        target: Any,
        title: str,
        markdown: str,
        reason: str = "",
        confidence: float | None = None,
        source_query: str = "",
        topic_path: list[str] | None = None,
        source_indices: list[dict[str, Any]] | None = None,
        entry_kind: str = "tracking_insight",
    ) -> Path | None:
        if not self.enabled:
            return None
        safe_markdown = str(markdown or "").strip()
        if not safe_markdown:
            return None
        try:
            meta = self._target_meta(target)
            now = _utcnow()
            ts = _iso(now) or _iso(_utcnow())
            ts_id = _slug(ts.replace(":", "").replace("+00:00", "Z"), fallback="t", max_len=48)
            title_text = str(title or "追踪洞察").strip()[:180] or "追踪洞察"
            score_text = ""
            if confidence is not None:
                try:
                    score = max(0.0, min(1.0, float(confidence)))
                    score_text = f"{score:.2f}"
                except Exception:
                    score_text = ""
            source_items: list[dict[str, Any]] = []
            if isinstance(source_indices, list):
                for row in source_indices[:20]:
                    if not isinstance(row, dict):
                        continue
                    source_items.append(
                        {
                            "type": str(row.get("type") or "unknown")[:32],
                            "label": str(row.get("label") or "")[:220],
                            "url": str(row.get("url") or "")[:500],
                            "path": str(row.get("path") or "")[:500],
                            "message_id": int(row.get("message_id") or 0),
                        }
                    )
            if source_query.strip():
                source_items.insert(
                    0,
                    {
                        "type": "query",
                        "label": source_query.strip()[:220],
                        "url": "",
                        "path": "",
                        "message_id": 0,
                    },
                )
            topic_parts = self._normalize_topic_path(topic_path, fallback=meta["source_type"] or "综合")
            topic_text = " > ".join(topic_parts)
            body = [
                "# Tracking Insight",
                "",
                f"- canonical_id: `{meta['canonical_id']}`",
                f"- target: {meta['display_name']}",
                f"- source: {meta['source_type']}",
                "- kind: insight",
                f"- entry_kind: {str(entry_kind or 'tracking_insight').strip()[:48]}",
                f"- topic_path: {topic_text}",
                f"- created_at: {ts}",
            ]
            if score_text:
                body.append(f"- confidence: {score_text}")
            if source_query.strip():
                body.append(f"- query: {source_query.strip()[:320]}")
            if reason.strip():
                body.append(f"- reason: {reason.strip()[:500]}")
            if source_items:
                body.extend(["- source_indices_json:"])
                body.extend([f"  {line}" for line in _safe_json(source_items).splitlines()])
            body.extend(["", "## Title", "", title_text, "", "## Insight", "", safe_markdown])
            if source_items:
                body.extend(["", "## 来源索引", ""])
                for row in source_items[:12]:
                    source_type = str(row.get("type") or "unknown")
                    label = str(row.get("label") or "").strip()
                    message_id = int(row.get("message_id") or 0)
                    url = str(row.get("url") or "").strip()
                    path = str(row.get("path") or "").strip()
                    line = f"- [{source_type}]"
                    if label:
                        line += f" {label}"
                    if message_id > 0:
                        line += f" | message_id={message_id}"
                    if url:
                        line += f" | url={url}"
                    if path:
                        line += f" | path={path}"
                    body.append(line)
            body.append("")

            content = "\n".join(body)
            file_name = f"{ts_id}_{_slug(title_text, fallback='insight', max_len=42)}.md"
            legacy_path = self._target_dir(target) / "insights" / file_name
            self._write_markdown(legacy_path, content)

            diary_dir = self._diary_root(
                user_id=int(meta["user_id"] or 0),
                workspace=meta["workspace"],
            )
            for part in topic_parts:
                diary_dir = diary_dir / _slug(part, fallback="topic", max_len=48)
            diary_path = diary_dir / file_name
            self._write_markdown(diary_path, content)
            return diary_path
        except Exception as exc:
            _LOG.warning("file-memory insight append failed: %s", exc)
            return None


    def search(
        self,
        *,
        user_id: int,
        workspace: str,
        query: str,
        limit: int | None = None,
        source: str | None = None,
    ) -> list[FileMemoryHit]:
        if not self.enabled:
            return []
        safe_limit = max(1, min(40, int(limit or self.query_limit)))
        query_text = (query or "").strip()
        try:
            if self._openviking is not None and query_text:
                hits = self._search_with_openviking(
                    user_id=user_id,
                    workspace=workspace,
                    query=query_text,
                    limit=safe_limit,
                    source=source,
                )
                if hits:
                    return hits[:safe_limit]
        except Exception as exc:
            _LOG.debug("openviking search failed, fallback to local: %s", exc)
        return self._search_local(
            user_id=user_id,
            workspace=workspace,
            query=query_text,
            limit=safe_limit,
            source=source,
        )

    def _local_cache_key(self, path: Path) -> str:
        try:
            return str(path.resolve()).lower()
        except Exception:
            return str(path).lower()

    def _prune_local_doc_cache(self) -> None:
        overflow = len(self._local_doc_cache) - self._local_cache_max_entries
        if overflow <= 0:
            return
        stale_keys = sorted(
            self._local_doc_cache.items(),
            key=lambda item: float(item[1].get("accessed_at") or 0.0),
        )[:overflow]
        for key, _ in stale_keys:
            self._local_doc_cache.pop(str(key), None)

    def _load_local_doc_entry(self, path: Path) -> tuple[float, str, dict[str, str]] | None:
        cache_key = self._local_cache_key(path)
        try:
            mtime = float(path.stat().st_mtime)
        except Exception:
            return None

        now = time.monotonic()
        with self._local_cache_lock:
            cached = self._local_doc_cache.get(cache_key)
            if cached is not None and float(cached.get("mtime") or -1.0) == mtime:
                text = str(cached.get("text") or "")
                meta = cached.get("meta") if isinstance(cached.get("meta"), dict) else {}
                cached["accessed_at"] = now
                if text.strip():
                    return mtime, text, {str(k): str(v) for k, v in meta.items()}

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None
        if not text.strip():
            return None
        meta = self._parse_markdown_meta(path, raw_text=text)
        with self._local_cache_lock:
            self._local_doc_cache[cache_key] = {
                "mtime": mtime,
                "text": text,
                "meta": meta,
                "accessed_at": now,
            }
            self._prune_local_doc_cache()
        return mtime, text, meta

    def _search_with_openviking(
        self,
        *,
        user_id: int,
        workspace: str,
        query: str,
        limit: int,
        source: str | None,
    ) -> list[FileMemoryHit]:
        client = self._openviking
        if client is None:
            return []
        out: list[FileMemoryHit] = []
        seen_paths: set[str] = set()
        for base_dir in self._candidate_search_dirs(user_id=user_id, workspace=workspace, source=source):
            if not base_dir.exists():
                continue
            raw: Any = None
            if hasattr(client, "search"):
                try:
                    raw = client.search(query=query, top_k=limit, base_dir=str(base_dir))
                except TypeError:
                    raw = client.search(query, limit)
            if not raw:
                continue
            rows = raw if isinstance(raw, list) else list(getattr(raw, "items", []) or [])
            for row in rows:
                path = str(getattr(row, "path", "") or row.get("path") or "").strip() if isinstance(row, dict) else str(getattr(row, "path", "")).strip()
                if not path:
                    continue
                preview = ""
                title = ""
                score = 0.0
                if isinstance(row, dict):
                    preview = str(row.get("preview") or row.get("snippet") or "")
                    title = str(row.get("title") or "")
                    score = float(row.get("score") or 0.0)
                else:
                    preview = str(getattr(row, "preview", "") or getattr(row, "snippet", "") or "")
                    title = str(getattr(row, "title", "") or "")
                    score = float(getattr(row, "score", 0.0) or 0.0)
                abs_path = Path(path) if Path(path).is_absolute() else (base_dir / path)
                key = str(abs_path).lower()
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                cached = self._load_local_doc_entry(abs_path)
                parsed = (
                    cached[2]
                    if isinstance(cached, tuple) and len(cached) >= 3 and isinstance(cached[2], dict)
                    else self._parse_markdown_meta(abs_path)
                )
                out.append(
                    FileMemoryHit(
                        path=str(abs_path),
                        title=title or parsed.get("title") or abs_path.name,
                        preview=preview or parsed.get("preview") or "",
                        score=max(0.0, score),
                        updated_at=parsed.get("updated_at") or _iso(_utcnow()),
                        canonical_id=parsed.get("canonical_id") or "",
                        target=parsed.get("target") or "",
                        source=parsed.get("source") or "",
                        kind=parsed.get("kind") or "",
                        topic_path=parsed.get("topic_path") or "",
                        entry_kind=parsed.get("entry_kind") or "",
                    )
                )
                if len(out) >= limit:
                    return out[:limit]
        return out

    def _search_local(
        self,
        *,
        user_id: int,
        workspace: str,
        query: str,
        limit: int,
        source: str | None,
    ) -> list[FileMemoryHit]:
        tokens = [it.lower() for it in _TOKEN_RE.findall(query.lower()) if len(it) >= 1][:16]
        rows: list[tuple[float, float, Path, dict[str, str], str]] = []
        seen_paths: set[str] = set()
        for base_dir in self._candidate_search_dirs(user_id=user_id, workspace=workspace, source=source):
            if not base_dir.exists():
                continue
            for path in base_dir.rglob("*.md"):
                key = str(path).lower()
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                loaded = self._load_local_doc_entry(path)
                if loaded is None:
                    continue
                ts, text, meta = loaded
                score = self._score_text(text, query=query, tokens=tokens)
                if query and score <= 0.0:
                    continue
                preview = meta.get("preview") or self._extract_preview(text)
                rows.append((score, ts, path, meta, preview))
        if not rows:
            return []

        rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
        out: list[FileMemoryHit] = []
        for score, ts, path, meta, preview in rows[: max(limit * 3, limit)]:
            out.append(
                FileMemoryHit(
                    path=str(path),
                    title=meta.get("title") or path.name,
                    preview=preview,
                    score=max(0.01, float(score)),
                    updated_at=meta.get("updated_at") or datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                    canonical_id=meta.get("canonical_id") or "",
                    target=meta.get("target") or "",
                    source=meta.get("source") or "",
                    kind=meta.get("kind") or "",
                    topic_path=meta.get("topic_path") or "",
                    entry_kind=meta.get("entry_kind") or "",
                )
            )
            if len(out) >= limit:
                break
        return out

    def _score_text(self, text: str, *, query: str, tokens: list[str]) -> float:
        lowered = text.lower()
        score = 0.0
        if query:
            q = query.lower().strip()
            if q and q in lowered:
                score += 5.0
        for tok in tokens:
            cnt = lowered.count(tok)
            if cnt > 0:
                score += min(6.0, 1.0 + cnt * 0.6)
        if "- kind: snapshot" in lowered:
            score -= 0.8
        if "- kind: change" in lowered:
            score -= 0.2
        if "- entry_kind: chat_diary" in lowered:
            score += 1.8
        if "- entry_kind: chat_parallel_draft" in lowered:
            score += 1.6
        if "- entry_kind: media_insight" in lowered:
            score += 1.4
        if "- entry_kind: tracking_insight" in lowered:
            score += 1.0
        if "## 提炼信息（日记）" in lowered:
            score += 1.2
        if "## 今日对话" in lowered:
            score += 1.2
        return score

    def _extract_preview(self, text: str) -> str:
        content = str(text or "")
        for marker in ("## 提炼信息（日记）", "## 今日对话", "## 总结", "## 概要", "## Summary", "## Insight"):
            idx = content.find(marker)
            if idx >= 0:
                content = content[idx:]
                break

        lines: list[str] = []
        for raw in content.splitlines():
            row = raw.strip()
            if not row:
                continue
            if row.startswith("#"):
                continue
            lowered = row.lower()
            if lowered.startswith("- canonical_id:") or lowered.startswith("- target:") or lowered.startswith("- source:"):
                continue
            if lowered.startswith("- kind:") or lowered.startswith("- created_at:") or lowered.startswith("- confidence:"):
                continue
            if lowered.startswith("- query:") or lowered.startswith("- reason:"):
                continue
            if lowered.startswith("- source_indices_json:"):
                continue
            lines.append(row)
            if len(" ".join(lines)) >= 420:
                break

        clean = re.sub(r"```[\s\S]*?```", " ", "\n".join(lines))
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:280]

    def _parse_markdown_meta(self, path: Path, raw_text: str | None = None) -> dict[str, str]:
        try:
            text = raw_text if raw_text is not None else path.read_text(encoding="utf-8")
        except Exception:
            return {}
        title = ""
        section_title = ""
        preview = ""
        canonical_id = ""
        target = ""
        source = ""
        kind = ""
        topic_path = ""
        entry_kind = ""
        updated_at = ""
        lines = text.splitlines()
        for idx, line in enumerate(lines[:60]):
            row = line.strip()
            if idx == 0 and row.startswith("#"):
                title = row.lstrip("#").strip()[:120]
            if row.lower().startswith("- canonical_id:"):
                canonical_id = row.split(":", 1)[-1].strip().strip("`")[:80]
            elif row.lower().startswith("- target:"):
                target = row.split(":", 1)[-1].strip()[:255]
            elif row.lower().startswith("- source:"):
                source = row.split(":", 1)[-1].strip()[:48]
            elif row.lower().startswith("- kind:"):
                kind = row.split(":", 1)[-1].strip()[:48]
            elif row.lower().startswith("- topic_path:"):
                topic_path = row.split(":", 1)[-1].strip()[:280]
            elif row.lower().startswith("- entry_kind:"):
                entry_kind = row.split(":", 1)[-1].strip()[:48]
            elif row.lower().startswith("- fetched_at:") or row.lower().startswith("- created_at:"):
                updated_at = row.split(":", 1)[-1].strip()[:80]
            elif row.lower().startswith("- updated_at:"):
                updated_at = row.split(":", 1)[-1].strip()[:80]
            elif row == "## Title":
                for next_row in lines[idx + 1 : idx + 6]:
                    candidate = next_row.strip()
                    if candidate and not candidate.startswith("#"):
                        section_title = candidate[:180]
                        break
        if section_title:
            title = section_title
        elif title.lower() == "tracking insight" and target:
            title = target[:120]
        preview = self._extract_preview(text)
        return {
            "title": title,
            "preview": preview,
            "canonical_id": canonical_id,
            "target": target,
            "source": source,
            "kind": kind,
            "topic_path": topic_path,
            "entry_kind": entry_kind,
            "updated_at": updated_at,
        }

    def list_diary_tree(
        self,
        *,
        user_id: int,
        workspace: str,
        max_files: int = 500,
    ) -> list[DiaryTreeNode]:
        if not self.enabled:
            return []
        root = self._diary_root(user_id=user_id, workspace=workspace)
        if not root.exists():
            return []

        limit = max(20, min(2000, int(max_files or 500)))
        visited_files = 0

        def _stat_iso(path: Path) -> str:
            try:
                return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            except Exception:
                return _iso(_utcnow())

        def _walk(dir_path: Path) -> list[DiaryTreeNode]:
            nonlocal visited_files
            out_nodes: list[DiaryTreeNode] = []
            children = []
            try:
                children = sorted(
                    list(dir_path.iterdir()),
                    key=lambda p: (0 if p.is_dir() else 1, p.name.lower()),
                )
            except Exception:
                return []

            for child in children:
                rel_path = child.relative_to(root).as_posix()
                if child.is_dir():
                    nested = _walk(child)
                    out_nodes.append(
                        DiaryTreeNode(
                            name=child.name,
                            path=rel_path,
                            kind="folder",
                            updated_at=_stat_iso(child),
                            children=nested,
                        )
                    )
                    continue
                if child.suffix.lower() != ".md":
                    continue
                if visited_files >= limit:
                    continue
                visited_files += 1
                meta = self._parse_markdown_meta(child)
                out_nodes.append(
                    DiaryTreeNode(
                        name=child.name,
                        path=rel_path,
                        kind="file",
                        title=meta.get("title") or child.name,
                        preview=meta.get("preview") or "",
                        updated_at=meta.get("updated_at") or _stat_iso(child),
                        source=meta.get("source") or "",
                        topic_path=meta.get("topic_path") or "",
                        entry_kind=meta.get("entry_kind") or "",
                    )
                )
            return out_nodes

        return _walk(root)

    def read_memory_markdown(
        self,
        *,
        user_id: int,
        workspace: str,
        path: str,
    ) -> dict[str, str] | None:
        if not self.enabled:
            return None
        raw_path = str(path or "").strip()
        if not raw_path:
            return None

        workspace_root = self._workspace_root(user_id=user_id, workspace=workspace).resolve()
        resolved: Path | None = None

        candidate = Path(raw_path)
        if candidate.is_absolute():
            try:
                abs_path = candidate.resolve()
                abs_path.relative_to(workspace_root)
                if abs_path.exists() and abs_path.is_file() and abs_path.suffix.lower() == ".md":
                    resolved = abs_path
            except Exception:
                resolved = None
        else:
            candidate_paths = [
                workspace_root / candidate,
                self._diary_root(user_id=user_id, workspace=workspace).resolve() / candidate,
                self._tracking_root(user_id=user_id, workspace=workspace).resolve() / candidate,
            ]
            for path_item in candidate_paths:
                try:
                    abs_path = path_item.resolve()
                    abs_path.relative_to(workspace_root)
                except Exception:
                    continue
                if abs_path.exists() and abs_path.is_file() and abs_path.suffix.lower() == ".md":
                    resolved = abs_path
                    break

        if resolved is None:
            return None

        loaded = self._load_local_doc_entry(resolved)
        if loaded is None:
            return None
        _ts, text, meta = loaded
        return {
            "path": str(resolved),
            "title": meta.get("title") or resolved.name,
            "source": meta.get("source") or "",
            "kind": meta.get("kind") or "",
            "topic_path": meta.get("topic_path") or "",
            "entry_kind": meta.get("entry_kind") or "",
            "updated_at": meta.get("updated_at") or _iso(_utcnow()),
            "content": text,
        }


tracking_file_memory_bridge = TrackingFileMemoryBridge()
