from __future__ import annotations

import hashlib
import importlib
import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.settings import settings

_LOG = logging.getLogger(__name__)
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def _slug(text: str, *, fallback: str = "item", max_len: int = 64) -> str:
    raw = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "-", (text or "").strip()).strip("-")
    if not raw:
        return fallback
    return raw[:max_len]


def _normalize_workspace(value: str) -> str:
    clean = " ".join((value or "").strip().split())
    return clean[:64] if clean else "default"


def _safe_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        return "{}"


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()


@dataclass(slots=True)
class FileMemoryHit:
    path: str
    title: str
    preview: str
    score: float
    updated_at: str
    canonical_id: str
    target: str
    source: str
    kind: str


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
        base_dir = self.root / "users" / str(int(user_id)) / "workspaces" / _slug(_normalize_workspace(workspace), fallback="default") / "tracking"
        if source:
            base_dir = base_dir / _slug(source.strip().lower(), fallback="web")
        if not base_dir.exists():
            return []

        raw: Any = None
        if hasattr(client, "search"):
            try:
                raw = client.search(query=query, top_k=limit, base_dir=str(base_dir))
            except TypeError:
                raw = client.search(query, limit)
        if not raw:
            return []
        rows = raw if isinstance(raw, list) else list(getattr(raw, "items", []) or [])
        out: list[FileMemoryHit] = []
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
            parsed = self._parse_markdown_meta(abs_path)
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
                )
            )
            if len(out) >= limit:
                break
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
        base_dir = self.root / "users" / str(int(user_id)) / "workspaces" / _slug(_normalize_workspace(workspace), fallback="default") / "tracking"
        if source:
            base_dir = base_dir / _slug(source.strip().lower(), fallback="web")
        if not base_dir.exists():
            return []

        tokens = [it.lower() for it in _TOKEN_RE.findall(query.lower()) if len(it) >= 1][:16]
        rows: list[tuple[float, float, Path, str]] = []
        for path in base_dir.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if not text.strip():
                continue
            score = self._score_text(text, query=query, tokens=tokens)
            if query and score <= 0.0:
                continue
            try:
                ts = path.stat().st_mtime
            except Exception:
                ts = 0.0
            rows.append((score, ts, path, text))
        if not rows:
            return []

        rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
        out: list[FileMemoryHit] = []
        for score, ts, path, text in rows[: max(limit * 3, limit)]:
            meta = self._parse_markdown_meta(path, raw_text=text)
            preview = meta.get("preview") or self._extract_preview(text)
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
            score += 0.4
        if "- kind: change" in lowered:
            score += 0.3
        return score

    def _extract_preview(self, text: str) -> str:
        clean = re.sub(r"```[\s\S]*?```", " ", text)
        clean = re.sub(r"#+\s*", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:280]

    def _parse_markdown_meta(self, path: Path, raw_text: str | None = None) -> dict[str, str]:
        try:
            text = raw_text if raw_text is not None else path.read_text(encoding="utf-8")
        except Exception:
            return {}
        title = ""
        preview = ""
        canonical_id = ""
        target = ""
        source = ""
        kind = ""
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
            elif row.lower().startswith("- fetched_at:") or row.lower().startswith("- created_at:"):
                updated_at = row.split(":", 1)[-1].strip()[:80]
            elif row.lower().startswith("- updated_at:"):
                updated_at = row.split(":", 1)[-1].strip()[:80]
        preview = self._extract_preview(text)
        return {
            "title": title,
            "preview": preview,
            "canonical_id": canonical_id,
            "target": target,
            "source": source,
            "kind": kind,
            "updated_at": updated_at,
        }


tracking_file_memory_bridge = TrackingFileMemoryBridge()
