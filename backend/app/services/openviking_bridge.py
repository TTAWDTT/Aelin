from __future__ import annotations

import importlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.settings import settings
from app.services.openviking_utils import (
    _TOKEN_RE,
    _iso,
    _normalize_workspace,
    _safe_json,
    _sha1,
    _slug,
    _utcnow,
    FileMemoryHit,
)

_LOG = logging.getLogger(__name__)


class _OpenVikingAdapter:
    """Thin compatibility adapter for different OpenViking Python SDK versions."""

    def __init__(self, *, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.client = self._build_client(root_dir=root_dir)

    def _build_client(self, *, root_dir: Path) -> Any | None:
        try:
            module = importlib.import_module("openviking")
        except Exception:
            return None
        client_cls = (
            getattr(module, "SyncOpenViking", None)
            or getattr(module, "OpenViking", None)
            or getattr(module, "Client", None)
        )
        if client_cls is None:
            return None
        candidates = (
            lambda: client_cls(root_dir=str(root_dir)),
            lambda: client_cls(path=str(root_dir)),
            lambda: client_cls(str(root_dir)),
            lambda: client_cls(),
        )
        for build in candidates:
            try:
                client = build()
            except TypeError:
                continue
            except Exception:
                continue
            initializer = getattr(client, "initialize", None)
            if callable(initializer):
                try:
                    initializer()
                except TypeError:
                    try:
                        initializer(str(root_dir))
                    except Exception:
                        pass
                except Exception:
                    pass
            return client
        return None

    @property
    def available(self) -> bool:
        return self.client is not None

    def add_resource(self, *, path: Path) -> dict[str, Any]:
        client = self.client
        if client is None:
            return {}
        fn = getattr(client, "add_resource", None) or getattr(client, "add", None)
        if not callable(fn):
            return {}
        payload: Any = None
        path_text = str(path)
        call_variants = (
            lambda: fn(path=path_text),
            lambda: fn(resource_path=path_text),
            lambda: fn(uri=path_text),
            lambda: fn(path_text),
        )
        for invoke in call_variants:
            try:
                payload = invoke()
                break
            except TypeError:
                continue
            except Exception:
                return {}
        if payload is None:
            return {}
        return self._normalize_payload(payload)

    def wait_processed(self, *, timeout_seconds: float) -> None:
        client = self.client
        if client is None:
            return
        fn = getattr(client, "wait_processed", None)
        if not callable(fn):
            return
        timeout = max(1.0, float(timeout_seconds or 0.0))
        for invoke in (
            lambda: fn(timeout=timeout),
            lambda: fn(timeout_seconds=timeout),
            lambda: fn(timeout),
            lambda: fn(),
        ):
            try:
                invoke()
                return
            except TypeError:
                continue
            except Exception:
                return

    def find(self, *, query: str, limit: int, target_uri: str | None) -> list[dict[str, Any]]:
        client = self.client
        if client is None:
            return []

        def _call_find() -> Any:
            fn = getattr(client, "find", None)
            if not callable(fn):
                return None
            variants: list[Any] = []
            if target_uri:
                variants = [
                    lambda: fn(query=query, top_k=limit, target_uri=target_uri),
                    lambda: fn(query=query, n_results=limit, target_uri=target_uri),
                    lambda: fn(query, limit, target_uri),
                ]
            else:
                variants = [
                    lambda: fn(query=query, top_k=limit),
                    lambda: fn(query=query, n_results=limit),
                    lambda: fn(query, limit),
                ]
            for invoke in variants:
                try:
                    return invoke()
                except TypeError:
                    continue
            return None

        def _call_search() -> Any:
            fn = getattr(client, "search", None)
            if not callable(fn):
                return None
            variants = [
                lambda: fn(query=query, top_k=limit, base_dir=target_uri or str(self.root_dir)),
                lambda: fn(query, limit),
                lambda: fn(query=query, top_k=limit),
            ]
            for invoke in variants:
                try:
                    return invoke()
                except TypeError:
                    continue
            return None

        raw = _call_find()
        if raw is None:
            raw = _call_search()
        if raw is None:
            return []
        rows = self._normalize_rows(raw)
        return rows[: max(1, int(limit))]

    def _normalize_rows(self, raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [self._normalize_payload(item) for item in raw]
        if isinstance(raw, dict):
            items = raw.get("items") or raw.get("results") or raw.get("resources")
            if isinstance(items, list):
                return [self._normalize_payload(item) for item in items]
            return [self._normalize_payload(raw)]
        for attr in ("items", "results", "resources"):
            items = getattr(raw, attr, None)
            if isinstance(items, list):
                return [self._normalize_payload(item) for item in items]
        return [self._normalize_payload(raw)]

    def _normalize_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        out: dict[str, Any] = {}
        for key in (
            "uri",
            "path",
            "resource_uri",
            "resource_path",
            "title",
            "preview",
            "snippet",
            "content",
            "text",
            "score",
            "root_uri",
            "base_uri",
        ):
            value = getattr(payload, key, None)
            if value is not None:
                out[key] = value
        try:
            as_dict = dict(payload)  # type: ignore[arg-type]
            if isinstance(as_dict, dict):
                out.update(as_dict)
        except Exception:
            pass
        return out


class FileMemoryBridge:
    """
    File-first memory projection for long-term memory entries.

    - Retrieval uses optional OpenViking SDK; falls back to local lexical scoring.
    """

    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "openviking_enabled", True))
        self.semantic_enabled = bool(getattr(settings, "openviking_semantic_enabled", True))
        self.sync_on_write = bool(getattr(settings, "openviking_sync_on_write", True))
        self.wait_processed_on_search = bool(getattr(settings, "openviking_wait_processed_on_search", False))
        self.resync_interval_seconds = max(10.0, float(getattr(settings, "openviking_resync_interval_seconds", 120.0)))
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
        self._openviking_lock = threading.Lock()
        self._openviking_dir_state: dict[str, dict[str, Any]] = {}
        self._openviking_uri_to_path: dict[str, str] = {}
        self._local_cache_lock = threading.Lock()
        self._local_cache_max_entries = max(
            200,
            min(20000, int(getattr(settings, "openviking_local_cache_max_entries", 2000) or 2000)),
        )
        self._local_doc_cache: dict[str, dict[str, Any]] = {}

    def _load_openviking(self) -> _OpenVikingAdapter | None:
        if (not self.enabled) or (not self.semantic_enabled):
            return None
        adapter = _OpenVikingAdapter(root_dir=self.root)
        if not adapter.available:
            return None
        return adapter

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
            / "memory"
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

    def _memory_root(self, *, user_id: int, workspace: str) -> Path:
        return self._workspace_root(user_id=user_id, workspace=workspace) / "memory"

    def read_agents_memory(
        self,
        *,
        user_id: int,
        workspace: str,
    ) -> str | None:
        """
        Read the workspace-level AGENTS.md memory file, if present.

        This is the canonical DeepAgents-style memory file used to provide
        persistent context for a given user + workspace pair.
        """
        if not self.enabled:
            return None
        memory_root = self._memory_root(user_id=user_id, workspace=workspace)
        path = (memory_root / "AGENTS.md").resolve()
        try:
            if not path.exists() or not path.is_file():
                return None
        except Exception:
            return None

        loaded = self._load_local_doc_entry(path)
        if loaded is None:
            return None
        _ts, text, _meta = loaded
        return text

    def write_agents_memory(
        self,
        *,
        user_id: int,
        workspace: str,
        content: str,
    ) -> str | None:
        """
        Overwrite the workspace-level AGENTS.md memory file with provided content.

        The file is stored under the user's memory root:
            users/{user_id}/workspaces/{workspace}/memory/AGENTS.md
        """
        if not self.enabled:
            return None
        text = str(content or "").strip()
        if not text:
            return None

        memory_root = self._memory_root(user_id=user_id, workspace=workspace)
        with self._io_lock:
            try:
                memory_root.mkdir(parents=True, exist_ok=True)
                path = (memory_root / "AGENTS.md").resolve()
                path.write_text(text, encoding="utf-8")
            except Exception:
                return None

        # Warm the local doc cache so subsequent reads are fast and consistent.
        try:
            self._load_local_doc_entry(path)
        except Exception:
            pass
        return str(path)

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
        memory_root = self._memory_root(user_id=user_id, workspace=workspace)
        out: list[Path] = []
        source_norm = str(source or "").strip().lower()
        if source_norm:
            out.append(memory_root / _slug(source_norm, fallback="web"))
        else:
            out.append(memory_root)
        return out

    def _extract_openviking_uri(self, payload: dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""
        for key in ("root_uri", "base_uri", "uri", "resource_uri"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        items = payload.get("items") or payload.get("resources") or payload.get("results")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    candidate = self._extract_openviking_uri(item)
                    if candidate:
                        return candidate
        return ""

    def _remember_openviking_path_mapping(self, *, payload: dict[str, Any], fallback_path: Path | None = None) -> None:
        if not isinstance(payload, dict):
            return
        uri = str(payload.get("uri") or payload.get("resource_uri") or "").strip()
        path_value = str(payload.get("path") or payload.get("resource_path") or "").strip()
        if (not path_value) and fallback_path is not None:
            path_value = str(fallback_path)
        if uri and path_value:
            self._openviking_uri_to_path[uri] = path_value
        items = payload.get("items") or payload.get("resources") or payload.get("results")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    self._remember_openviking_path_mapping(payload=item, fallback_path=fallback_path)

    def _register_openviking_dir(self, base_dir: Path, *, force: bool = False) -> str:
        adapter = self._openviking
        if adapter is None:
            return ""
        if not base_dir.exists():
            return ""
        key = self._local_cache_key(base_dir.resolve())
        now = time.monotonic()
        with self._openviking_lock:
            state = self._openviking_dir_state.get(key) or {}
            last_sync = float(state.get("last_sync") or 0.0)
            cached_uri = str(state.get("uri") or "")
            if (not force) and cached_uri and (now - last_sync) < self.resync_interval_seconds:
                return cached_uri

        payload = adapter.add_resource(path=base_dir)
        uri = self._extract_openviking_uri(payload)
        with self._openviking_lock:
            self._openviking_dir_state[key] = {"uri": uri, "last_sync": now}
            self._remember_openviking_path_mapping(payload=payload, fallback_path=base_dir)
        return uri

    def _sync_openviking_path(self, path: Path) -> None:
        adapter = self._openviking
        if adapter is None or (not self.sync_on_write):
            return
        if (not path.exists()) or path.suffix.lower() != ".md":
            return
        try:
            self._register_openviking_dir(path.parent, force=False)
            payload = adapter.add_resource(path=path)
            with self._openviking_lock:
                self._remember_openviking_path_mapping(payload=payload, fallback_path=path)
        except Exception as exc:
            _LOG.debug("openviking add_resource failed: %s", exc)

    def _resolve_openviking_hit_path(self, *, base_dir: Path, row: dict[str, Any], target_uri: str) -> Path | None:
        row_path = str(row.get("path") or row.get("resource_path") or "").strip()
        if row_path:
            candidate = Path(row_path)
            if not candidate.is_absolute():
                candidate = (base_dir / row_path).resolve()
            if candidate.exists():
                return candidate

        row_uri = str(row.get("uri") or row.get("resource_uri") or "").strip()
        if row_uri:
            with self._openviking_lock:
                mapped = self._openviking_uri_to_path.get(row_uri)
            if mapped:
                mapped_path = Path(mapped)
                if mapped_path.exists():
                    return mapped_path.resolve()
            parsed = urlparse(row_uri)
            if parsed.scheme == "file":
                local_path = Path(unquote(parsed.path))
                if local_path.exists():
                    return local_path.resolve()
            if target_uri and row_uri.startswith(target_uri):
                suffix = row_uri[len(target_uri) :].lstrip("/\\")
                if suffix:
                    candidate = (base_dir / suffix).resolve()
                    if candidate.exists():
                        return candidate
        return None

    def _write_markdown(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with self._io_lock:
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(path)
        self._sync_openviking_path(path)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with self._io_lock:
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(path)

    def _read_json_file(self, path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _read_sidecar_meta(self, md_path: Path) -> dict[str, Any]:
        return self._read_json_file(md_path.with_suffix(".meta.json"))

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
        entry_kind: str = "memory_insight",
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
            title_text = str(title or "长期记忆洞察").strip()[:180] or "长期记忆洞察"
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
                "# Memory Insight",
                "",
                f"- canonical_id: `{meta['canonical_id']}`",
                f"- target: {meta['display_name']}",
                f"- source: {meta['source_type']}",
                "- kind: insight",
                f"- entry_kind: {str(entry_kind or 'memory_insight').strip()[:48]}",
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
            sidecar_meta = {
                "canonical_id": meta["canonical_id"],
                "target": meta["display_name"],
                "source": meta["source_type"],
                "entry_kind": str(entry_kind or "memory_insight").strip()[:48],
                "topic_path": topic_parts,
                "created_at": ts,
                "title": title_text,
                "query": source_query.strip()[:320],
                "reason": reason.strip()[:500],
                "confidence": score_text,
                "source_indices": source_items,
            }
            self._write_json(legacy_path.with_suffix(".meta.json"), sidecar_meta)
            return legacy_path
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
        adapter = self._openviking
        if adapter is None:
            return []
        out: list[FileMemoryHit] = []
        seen_paths: set[str] = set()
        for base_dir in self._candidate_search_dirs(
            user_id=user_id,
            workspace=workspace,
            source=source,
        ):
            if not base_dir.exists():
                continue
            target_uri = self._register_openviking_dir(base_dir, force=False)
            if self.wait_processed_on_search:
                adapter.wait_processed(timeout_seconds=max(2.0, self.resync_interval_seconds))
            rows = adapter.find(
                query=query,
                limit=max(limit * 3, limit),
                target_uri=target_uri or None,
            )
            if not rows:
                continue
            for row in rows:
                row_payload = dict(row) if isinstance(row, dict) else {}
                abs_path = self._resolve_openviking_hit_path(
                    base_dir=base_dir,
                    row=row_payload,
                    target_uri=target_uri,
                )
                if abs_path is None:
                    continue
                key = str(abs_path).lower()
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                preview = str(row_payload.get("preview") or row_payload.get("snippet") or row_payload.get("content") or row_payload.get("text") or "")
                title = str(row_payload.get("title") or "")
                score = float(row_payload.get("score") or 0.0)
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
        for base_dir in self._candidate_search_dirs(
            user_id=user_id,
            workspace=workspace,
            source=source,
        ):
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
        lexical_hit = False
        if query:
            q = query.lower().strip()
            if q and q in lowered:
                score += 5.0
                lexical_hit = True
        for tok in tokens:
            cnt = lowered.count(tok)
            if cnt > 0:
                score += min(6.0, 1.0 + cnt * 0.6)
                lexical_hit = True
        if query and (not lexical_hit):
            return 0.0
        if "- kind: snapshot" in lowered:
            score -= 0.8
        if "- kind: change" in lowered:
            score -= 0.2
        if "- entry_kind: media_insight" in lowered:
            score += 1.4
        if "- entry_kind: memory_insight" in lowered:
            score += 1.0
        return score

    def _extract_preview(self, text: str) -> str:
        content = str(text or "")
        for marker in ("## 总结", "## 概要", "## Summary", "## Insight"):
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
        elif title.lower() == "memory insight" and target:
            title = target[:120]
        sidecar = self._read_sidecar_meta(path)
        if sidecar:
            if not title:
                title = str(sidecar.get("title") or "").strip()[:120]
            if not source:
                source = str(sidecar.get("source") or "").strip()[:48]
            if not topic_path:
                side_topic = sidecar.get("topic_path")
                if isinstance(side_topic, list):
                    topic_path = " > ".join(str(it).strip()[:64] for it in side_topic if str(it).strip())[:280]
                else:
                    topic_path = str(sidecar.get("topic_path") or "").strip()[:280]
            if not entry_kind:
                entry_kind = str(sidecar.get("entry_kind") or "").strip()[:48]
            if not updated_at:
                updated_at = str(sidecar.get("created_at") or sidecar.get("updated_at") or "").strip()[:80]
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
                self._memory_root(user_id=user_id, workspace=workspace).resolve() / candidate,
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


file_memory_bridge = FileMemoryBridge()
