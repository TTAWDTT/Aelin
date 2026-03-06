from __future__ import annotations

import hashlib
import io
import json
import math
import re
import subprocess
import tempfile
import threading
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AttachmentChunk, AttachmentDocument
from app.settings import settings
from app.services.aelin_utils import escape_sql_like, normalize_positive_ints

try:
    from defusedxml import ElementTree as _SAFE_ET  # type: ignore
except Exception:
    _SAFE_ET = ET

_TEXT_FILE_EXTENSIONS = {
    "txt",
    "md",
    "markdown",
    "json",
    "csv",
    "xml",
    "yaml",
    "yml",
    "log",
    "ini",
    "conf",
    "html",
    "htm",
    "py",
    "js",
    "ts",
}
_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp", "gif"}
_OOXML_EXTENSIONS = {"docx", "pptx", "xlsx"}
_LEGACY_TO_MODERN = {"doc": "docx", "ppt": "pptx", "xls": "xlsx"}
_SUPPORTED_EXTENSIONS = _TEXT_FILE_EXTENSIONS | _IMAGE_EXTENSIONS | _OOXML_EXTENSIONS | {"pdf"} | set(_LEGACY_TO_MODERN)
_WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_DRAWING_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
_XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rels": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")
_WS_RE = re.compile(r"\s+")


class AttachmentIngestError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code or "attachment_ingest_error").strip() or "attachment_ingest_error"
        self.message = str(message or "attachment ingest failed").strip() or "attachment ingest failed"


@dataclass(slots=True)
class ParsedBlock:
    content: str
    block_type: str
    loc: dict[str, Any]


class AelinAttachmentService:
    def __init__(self) -> None:
        root = Path(str(getattr(settings, "aelin_attachment_storage_dir", "./data/aelin_attachments") or "./data/aelin_attachments"))
        self._root = root
        self._chunk_size = max(280, int(getattr(settings, "aelin_attachment_chunk_size", 700) or 700))
        self._chunk_overlap = max(20, min(self._chunk_size - 40, int(getattr(settings, "aelin_attachment_chunk_overlap", 120) or 120)))
        self._max_size = max(256 * 1024, int(getattr(settings, "aelin_attachment_max_size_bytes", 30 * 1024 * 1024) or (30 * 1024 * 1024)))
        self._soffice_bin = str(getattr(settings, "aelin_attachment_soffice_bin", "soffice") or "soffice").strip() or "soffice"
        self._legacy_convert_timeout_seconds = max(
            10,
            int(getattr(settings, "aelin_attachment_legacy_convert_timeout_seconds", 30) or 30),
        )

    @staticmethod
    def _normalize_workspace(raw: str) -> str:
        clean = " ".join(str(raw or "").strip().split())
        return (clean[:64] if clean else "default") or "default"

    @staticmethod
    def _normalize_session(raw: str) -> str:
        clean = " ".join(str(raw or "").strip().split())
        return clean[:64]

    @staticmethod
    def _normalize_name(raw: str) -> str:
        name = str(raw or "").strip().replace("\\", "/").split("/")[-1]
        return (name[:255] if name else "attachment")

    @staticmethod
    def _detect_ext(file_name: str) -> str:
        suffix = Path(file_name).suffix.lower().lstrip(".")
        return suffix[:16]

    @staticmethod
    def _safe_json(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return "{}"

    @staticmethod
    def _norm_text(text: str) -> str:
        return _WS_RE.sub(" ", str(text or "")).strip()

    @property
    def max_size_bytes(self) -> int:
        return int(self._max_size)

    def normalize_workspace(self, raw: str) -> str:
        return self._normalize_workspace(raw)

    def normalize_session(self, raw: str) -> str:
        return self._normalize_session(raw)

    @staticmethod
    def _xml_fromstring(raw: bytes | str) -> ET.Element:
        return _SAFE_ET.fromstring(raw)

    def _tokenize(self, text: str) -> list[str]:
        lowered = str(text or "").lower()
        if not lowered:
            return []
        out: list[str] = []
        for token in _TOKEN_RE.findall(lowered):
            token = token.strip()
            if not token:
                continue
            out.append(token)
            if re.fullmatch(r"[\u4e00-\u9fff]{4,}", token):
                for i in range(0, len(token) - 1):
                    out.append(token[i : i + 2])
        return out[:600]

    def _chunk_text(self, text: str) -> list[str]:
        clean = str(text or "").strip()
        if not clean:
            return []
        if len(clean) <= self._chunk_size:
            return [clean]
        step = max(80, self._chunk_size - self._chunk_overlap)
        chunks: list[str] = []
        start = 0
        while start < len(clean):
            end = min(len(clean), start + self._chunk_size)
            chunk = clean[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(clean):
                break
            start += step
        return chunks[:500]

    def _build_chunk_rows(self, blocks: list[ParsedBlock], fallback_text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        chunk_idx = 0
        for block in blocks:
            for piece in self._chunk_text(block.content):
                tokens = self._tokenize(piece)
                vec = Counter(tokens)
                rows.append(
                    {
                        "chunk_index": chunk_idx,
                        "text": piece,
                        "token_count": len(tokens),
                        "keyword_vector_json": self._safe_json(dict(vec.most_common(64))),
                        "loc_json": self._safe_json(dict(block.loc or {})),
                    }
                )
                chunk_idx += 1

        if rows:
            return rows

        for piece in self._chunk_text(fallback_text):
            tokens = self._tokenize(piece)
            rows.append(
                {
                    "chunk_index": chunk_idx,
                    "text": piece,
                    "token_count": len(tokens),
                    "keyword_vector_json": self._safe_json(dict(Counter(tokens).most_common(64))),
                    "loc_json": "{}",
                }
            )
            chunk_idx += 1
        return rows

    def _decode_text_file(self, content: bytes) -> str:
        for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "latin-1"):
            try:
                return str(content.decode(enc))
            except Exception:
                continue
        return str(content.decode("utf-8", errors="ignore"))

    @staticmethod
    def _extract_word_table(tbl: ET.Element) -> list[list[str]]:
        rows: list[list[str]] = []
        for row in tbl.findall(".//w:tr", _WORD_NS):
            row_cells: list[str] = []
            for cell in row.findall(".//w:tc", _WORD_NS):
                text = "".join(t.text or "" for t in cell.findall(".//w:t", _WORD_NS))
                row_cells.append(_WS_RE.sub(" ", text).strip())
            if any(cell for cell in row_cells):
                rows.append(row_cells)
        return rows

    def _parse_docx(self, content: bytes, *, file_name: str) -> tuple[str, list[ParsedBlock], dict[str, Any]]:
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except Exception as exc:
            raise AttachmentIngestError("docx_invalid_zip", f"DOCX 文件损坏或无法读取: {exc}") from exc

        try:
            raw = zf.read("word/document.xml")
        except Exception as exc:
            raise AttachmentIngestError("docx_missing_document_xml", f"DOCX 缺少主文档结构: {exc}") from exc

        try:
            root = self._xml_fromstring(raw)
        except Exception as exc:
            raise AttachmentIngestError("docx_xml_parse_failed", f"DOCX XML 解析失败: {exc}") from exc

        blocks: list[ParsedBlock] = []
        body = root.find("w:body", _WORD_NS)
        para_idx = 0
        table_idx = 0
        if body is not None:
            for child in list(body):
                tag = str(child.tag)
                if tag.endswith("}p"):
                    txt = "".join(t.text or "" for t in child.findall(".//w:t", _WORD_NS))
                    text = self._norm_text(txt)
                    if text:
                        para_idx += 1
                        blocks.append(ParsedBlock(content=text, block_type="paragraph", loc={"paragraph": para_idx}))
                elif tag.endswith("}tbl"):
                    rows = self._extract_word_table(child)
                    if rows:
                        table_idx += 1
                        flat = "\n".join(" | ".join(cell for cell in row if cell) for row in rows if any(row))
                        blocks.append(
                            ParsedBlock(
                                content=f"[table {table_idx}]\n{flat}".strip(),
                                block_type="table",
                                loc={"table": table_idx},
                            )
                        )

        media_names = [name for name in zf.namelist() if name.startswith("word/media/")]
        for idx, media_name in enumerate(media_names, start=1):
            blocks.append(
                ParsedBlock(
                    content=f"[image {idx}] {Path(media_name).name}",
                    block_type="image_meta",
                    loc={"image": idx},
                )
            )

        full_text = "\n".join(block.content for block in blocks if block.content).strip()
        if not full_text:
            raise AttachmentIngestError("docx_empty_text", f"未从 DOCX 提取到可索引文本: {file_name}")

        metadata = {
            "parser": "docx_ooxml",
            "paragraph_count": para_idx,
            "table_count": table_idx,
            "image_count": len(media_names),
        }
        return full_text, blocks, metadata

    def _parse_pptx(self, content: bytes, *, file_name: str) -> tuple[str, list[ParsedBlock], dict[str, Any]]:
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except Exception as exc:
            raise AttachmentIngestError("pptx_invalid_zip", f"PPTX 文件损坏或无法读取: {exc}") from exc

        slide_entries: list[tuple[int, str]] = []
        for path in zf.namelist():
            if not (path.startswith("ppt/slides/slide") and path.endswith(".xml")):
                continue
            match = re.search(r"slide(\d+)\.xml$", path)
            if not match:
                continue
            slide_entries.append((int(match.group(1)), path))

        if not slide_entries:
            raise AttachmentIngestError("pptx_missing_slides", f"PPTX 未找到 slides 结构: {file_name}")
        slide_entries.sort(key=lambda item: item[0])

        blocks: list[ParsedBlock] = []
        for slide_no, slide_path in slide_entries:
            try:
                raw = zf.read(slide_path)
                root = self._xml_fromstring(raw)
            except Exception:
                continue
            texts = [self._norm_text(node.text or "") for node in root.findall(".//a:t", _DRAWING_NS)]
            joined = "\n".join(t for t in texts if t)
            if joined:
                blocks.append(ParsedBlock(content=joined, block_type="slide", loc={"slide": slide_no}))

            notes_path = f"ppt/notesSlides/notesSlide{slide_no}.xml"
            if notes_path in zf.namelist():
                try:
                    notes_raw = zf.read(notes_path)
                    notes_root = self._xml_fromstring(notes_raw)
                    note_texts = [self._norm_text(node.text or "") for node in notes_root.findall(".//a:t", _DRAWING_NS)]
                    notes_joined = "\n".join(t for t in note_texts if t)
                    if notes_joined:
                        blocks.append(ParsedBlock(content=notes_joined, block_type="notes", loc={"slide": slide_no, "section": "notes"}))
                except Exception:
                    pass

        media_names = [name for name in zf.namelist() if name.startswith("ppt/media/")]
        for idx, media_name in enumerate(media_names, start=1):
            blocks.append(ParsedBlock(content=f"[image {idx}] {Path(media_name).name}", block_type="image_meta", loc={"image": idx}))

        full_text = "\n".join(block.content for block in blocks if block.content).strip()
        if not full_text:
            raise AttachmentIngestError("pptx_empty_text", f"未从 PPTX 提取到可索引文本: {file_name}")

        metadata = {
            "parser": "pptx_ooxml",
            "slide_count": len(slide_entries),
            "image_count": len(media_names),
        }
        return full_text, blocks, metadata

    def _xlsx_shared_strings(self, zf: zipfile.ZipFile) -> list[str]:
        path = "xl/sharedStrings.xml"
        if path not in zf.namelist():
            return []
        try:
            root = self._xml_fromstring(zf.read(path))
        except Exception:
            return []
        values: list[str] = []
        for si in root.findall(".//main:si", _XLSX_NS):
            parts = [node.text or "" for node in si.findall(".//main:t", _XLSX_NS)]
            values.append(_WS_RE.sub(" ", "".join(parts)).strip())
        return values

    def _xlsx_sheet_paths(self, zf: zipfile.ZipFile) -> list[tuple[str, str]]:
        try:
            wb_root = self._xml_fromstring(zf.read("xl/workbook.xml"))
            rels_root = self._xml_fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        except Exception:
            return []

        rel_map: dict[str, str] = {}
        for rel in rels_root.findall(".//rels:Relationship", _XLSX_NS):
            rid = str(rel.attrib.get("Id") or "").strip()
            target = str(rel.attrib.get("Target") or "").strip()
            if rid and target:
                rel_map[rid] = target

        out: list[tuple[str, str]] = []
        for sheet in wb_root.findall(".//main:sheets/main:sheet", _XLSX_NS):
            name = str(sheet.attrib.get("name") or "").strip() or "sheet"
            rel_id = str(sheet.attrib.get(f"{{{_XLSX_NS['r']}}}id") or "").strip()
            rel_target = rel_map.get(rel_id, "")
            if not rel_target:
                continue
            norm = rel_target.lstrip("/")
            if not norm.startswith("xl/"):
                norm = f"xl/{norm}"
            out.append((name[:120], norm))
        return out

    def _parse_xlsx(self, content: bytes, *, file_name: str) -> tuple[str, list[ParsedBlock], dict[str, Any]]:
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except Exception as exc:
            raise AttachmentIngestError("xlsx_invalid_zip", f"XLSX 文件损坏或无法读取: {exc}") from exc

        shared = self._xlsx_shared_strings(zf)
        sheets = self._xlsx_sheet_paths(zf)
        if not sheets:
            raise AttachmentIngestError("xlsx_missing_sheets", f"XLSX 缺少工作表结构: {file_name}")

        blocks: list[ParsedBlock] = []
        for sheet_name, path in sheets:
            if path not in zf.namelist():
                continue
            try:
                root = self._xml_fromstring(zf.read(path))
            except Exception:
                continue
            for row in root.findall(".//main:sheetData/main:row", _XLSX_NS):
                row_num = int(row.attrib.get("r") or 0)
                pairs: list[str] = []
                for cell in row.findall("main:c", _XLSX_NS):
                    cell_ref = str(cell.attrib.get("r") or "").strip()
                    cell_type = str(cell.attrib.get("t") or "").strip()
                    value_text = ""
                    if cell_type == "s":
                        idx_text = (cell.findtext("main:v", default="", namespaces=_XLSX_NS) or "").strip()
                        if idx_text.isdigit():
                            idx = int(idx_text)
                            if 0 <= idx < len(shared):
                                value_text = shared[idx]
                    elif cell_type == "inlineStr":
                        value_text = "".join(node.text or "" for node in cell.findall(".//main:t", _XLSX_NS))
                    else:
                        value_text = cell.findtext("main:v", default="", namespaces=_XLSX_NS) or ""
                    value_text = self._norm_text(value_text)
                    if cell_ref and value_text:
                        pairs.append(f"{cell_ref}={value_text}")
                if pairs:
                    blocks.append(
                        ParsedBlock(
                            content=" | ".join(pairs),
                            block_type="row",
                            loc={"sheet": sheet_name, "row": row_num},
                        )
                    )

        full_text = "\n".join(block.content for block in blocks if block.content).strip()
        if not full_text:
            raise AttachmentIngestError("xlsx_empty_text", f"未从 XLSX 提取到可索引文本: {file_name}")
        metadata = {"parser": "xlsx_ooxml", "sheet_count": len(sheets)}
        return full_text, blocks, metadata

    def _parse_pdf(self, content: bytes, *, file_name: str) -> tuple[str, list[ParsedBlock], dict[str, Any]]:
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception as exc:
            raise AttachmentIngestError("pdf_parser_unavailable", f"当前环境缺少 PDF 解析依赖 pypdf: {exc}") from exc

        try:
            reader = PdfReader(io.BytesIO(content))
        except Exception as exc:
            raise AttachmentIngestError("pdf_open_failed", f"PDF 打开失败: {exc}") from exc

        blocks: list[ParsedBlock] = []
        for page_idx, page in enumerate(reader.pages, start=1):
            text = self._norm_text(page.extract_text() or "")
            if text:
                blocks.append(ParsedBlock(content=text, block_type="page", loc={"page": page_idx}))
        full_text = "\n".join(block.content for block in blocks).strip()
        if not full_text:
            raise AttachmentIngestError(
                "pdf_text_layer_empty",
                f"PDF 为扫描件或不含可提取文本，当前版本暂不支持 OCR 兜底: {file_name}",
            )
        metadata = {"parser": "pdf_text_layer", "page_count": len(reader.pages)}
        return full_text, blocks, metadata

    def _parse_image(self, content: bytes, *, file_name: str) -> tuple[str, list[ParsedBlock], dict[str, Any]]:
        width = 0
        height = 0
        ocr_text = ""
        try:
            from PIL import Image  # type: ignore

            image = Image.open(io.BytesIO(content))
            width, height = int(image.width or 0), int(image.height or 0)
            try:
                import pytesseract  # type: ignore

                ocr_text = self._norm_text(pytesseract.image_to_string(image) or "")
            except Exception:
                ocr_text = ""
        except Exception:
            width = 0
            height = 0

        summary_text = ocr_text or f"图片文件: {file_name}（当前未启用 OCR，仅索引文件信息）"
        blocks = [ParsedBlock(content=summary_text, block_type="image", loc={"page": 1})]
        metadata = {"parser": ("image_ocr" if ocr_text else "image_meta"), "width": width, "height": height}
        return summary_text, blocks, metadata

    def _convert_legacy_office(self, content: bytes, *, ext: str) -> tuple[bytes, str]:
        target_ext = _LEGACY_TO_MODERN.get(ext, "")
        if not target_ext:
            raise AttachmentIngestError("legacy_format_unsupported", f"不支持的旧格式: {ext}")
        with tempfile.TemporaryDirectory(prefix="aelin-att-") as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / f"input.{ext}"
            input_path.write_bytes(content)
            cmd = [
                self._soffice_bin,
                "--headless",
                "--convert-to",
                target_ext,
                "--outdir",
                str(temp_path),
                str(input_path),
            ]
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self._legacy_convert_timeout_seconds,
                )
            except Exception as exc:
                raise AttachmentIngestError(
                    "legacy_convert_failed",
                    f"旧格式 {ext} 转换失败，请安装 LibreOffice/soffice 并确认可执行: {exc}",
                ) from exc
            converted = temp_path / f"input.{target_ext}"
            if not converted.exists():
                raise AttachmentIngestError("legacy_convert_missing_output", f"旧格式 {ext} 转换后未生成 {target_ext}")
            return converted.read_bytes(), target_ext

    def _parse_content(
        self,
        *,
        content: bytes,
        file_name: str,
        ext: str,
        mime_type: str,
    ) -> tuple[str, list[ParsedBlock], dict[str, Any]]:
        lower_ext = str(ext or "").lower().strip()
        if lower_ext in _LEGACY_TO_MODERN:
            converted_bytes, converted_ext = self._convert_legacy_office(content, ext=lower_ext)
            parsed_text, blocks, metadata = self._parse_content(
                content=converted_bytes,
                file_name=f"{file_name}.{converted_ext}",
                ext=converted_ext,
                mime_type=mime_type,
            )
            metadata = dict(metadata or {})
            metadata["converted_from"] = lower_ext
            return parsed_text, blocks, metadata

        if lower_ext in _TEXT_FILE_EXTENSIONS:
            text = self._norm_text(self._decode_text_file(content))
            if not text:
                raise AttachmentIngestError("text_empty", f"文本附件为空: {file_name}")
            return text, [ParsedBlock(content=text, block_type="text", loc={"offset": 0})], {"parser": "text"}

        if lower_ext == "pdf":
            return self._parse_pdf(content, file_name=file_name)
        if lower_ext == "docx":
            return self._parse_docx(content, file_name=file_name)
        if lower_ext == "pptx":
            return self._parse_pptx(content, file_name=file_name)
        if lower_ext == "xlsx":
            return self._parse_xlsx(content, file_name=file_name)
        if lower_ext in _IMAGE_EXTENSIONS or str(mime_type or "").lower().startswith("image/"):
            return self._parse_image(content, file_name=file_name)

        raise AttachmentIngestError("unsupported_type", f"暂不支持解析该文件类型: {file_name}")

    def ingest_bytes(
        self,
        db: Session,
        *,
        user_id: int,
        workspace: str,
        session_id: str,
        file_name: str,
        mime_type: str,
        content: bytes,
    ) -> dict[str, Any]:
        safe_name = self._normalize_name(file_name)
        ext = self._detect_ext(safe_name)
        if ext not in _SUPPORTED_EXTENSIONS:
            raise AttachmentIngestError("unsupported_extension", f"不支持的附件扩展名: .{ext or 'unknown'}")

        size = len(content or b"")
        if size <= 0:
            raise AttachmentIngestError("empty_file", "附件为空，无法上传")
        if size > self._max_size:
            raise AttachmentIngestError("file_too_large", f"附件过大（>{self._max_size} 字节）")

        workspace_norm = self._normalize_workspace(workspace)
        session_norm = self._normalize_session(session_id)
        file_sha = hashlib.sha256(content).hexdigest()

        existing = db.scalar(
            select(AttachmentDocument).where(
                AttachmentDocument.user_id == int(user_id),
                AttachmentDocument.workspace == workspace_norm,
                AttachmentDocument.sha256 == file_sha,
                AttachmentDocument.parse_status == "ready",
            )
        )
        if existing is not None:
            chunk_count = db.query(AttachmentChunk).filter(AttachmentChunk.attachment_id == int(existing.id)).count()
            return {
                "attachment_id": int(existing.id),
                "file_name": str(existing.file_name or safe_name),
                "mime_type": str(existing.mime_type or mime_type or ""),
                "size_bytes": int(existing.size_bytes or size),
                "workspace": workspace_norm,
                "session_id": str(existing.session_id or session_norm),
                "status": "ready",
                "chunk_count": int(chunk_count),
                "summary": str(existing.summary or "")[:220],
                "deduplicated": True,
            }

        user_dir = self._root / f"user_{int(user_id)}"
        shard_dir = user_dir / file_sha[:2]
        shard_dir.mkdir(parents=True, exist_ok=True)
        storage_name = f"{file_sha}.{ext}"
        storage_path = shard_dir / storage_name
        try:
            if not storage_path.exists():
                storage_path.write_bytes(content)

            parsed_text, blocks, metadata = self._parse_content(
                content=content,
                file_name=safe_name,
                ext=ext,
                mime_type=mime_type,
            )
            chunk_rows = self._build_chunk_rows(blocks=blocks, fallback_text=parsed_text)
            if not chunk_rows:
                raise AttachmentIngestError("chunk_build_failed", "附件解析后未生成可检索分块")
            summary = self._norm_text(parsed_text)[:220]

            row = AttachmentDocument(
                user_id=int(user_id),
                workspace=workspace_norm,
                session_id=session_norm,
                file_name=safe_name,
                file_ext=ext,
                mime_type=str(mime_type or "")[:160],
                size_bytes=size,
                sha256=file_sha,
                storage_path=str(storage_path.as_posix())[:1024],
                parse_status="ready",
                parse_error=None,
                summary=summary,
                metadata_json=self._safe_json(metadata),
            )
            db.add(row)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                existing = db.scalar(
                    select(AttachmentDocument).where(
                        AttachmentDocument.user_id == int(user_id),
                        AttachmentDocument.workspace == workspace_norm,
                        AttachmentDocument.sha256 == file_sha,
                        AttachmentDocument.parse_status == "ready",
                    )
                )
                if existing is None:
                    raise AttachmentIngestError("attachment_target_busy", "target is busy,retry in a few seconds") from None
                chunk_count = db.query(AttachmentChunk).filter(AttachmentChunk.attachment_id == int(existing.id)).count()
                return {
                    "attachment_id": int(existing.id),
                    "file_name": str(existing.file_name or safe_name),
                    "mime_type": str(existing.mime_type or mime_type or ""),
                    "size_bytes": int(existing.size_bytes or size),
                    "workspace": workspace_norm,
                    "session_id": str(existing.session_id or session_norm),
                    "status": "ready",
                    "chunk_count": int(chunk_count),
                    "summary": str(existing.summary or "")[:220],
                    "deduplicated": True,
                }

            for chunk in chunk_rows:
                db.add(
                    AttachmentChunk(
                        attachment_id=int(row.id),
                        chunk_index=int(chunk["chunk_index"]),
                        text=str(chunk["text"]),
                        token_count=int(chunk["token_count"]),
                        keyword_vector_json=str(chunk["keyword_vector_json"]),
                        loc_json=str(chunk["loc_json"]),
                    )
                )

            return {
                "attachment_id": int(row.id),
                "file_name": safe_name,
                "mime_type": str(mime_type or ""),
                "size_bytes": int(size),
                "workspace": workspace_norm,
                "session_id": session_norm,
                "status": "ready",
                "chunk_count": len(chunk_rows),
                "summary": summary,
                "deduplicated": False,
            }
        except Exception:
            raise

    @staticmethod
    def cleanup_storage_path(storage_path: str | Path | None) -> None:
        raw = str(storage_path or "").strip()
        if not raw:
            return
        path = Path(raw)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def _safe_load_json(raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def search(
        self,
        db: Session,
        *,
        user_id: int,
        workspace: str,
        query: str,
        attachment_ids: list[int],
        top_k: int = 5,
        mode: str = "keyword",
    ) -> dict[str, Any]:
        workspace_norm = self._normalize_workspace(workspace)
        q = self._norm_text(query)
        if not q:
            return {"ok": False, "error": "missing query"}
        ids = normalize_positive_ints(attachment_ids, cap=20)
        if not ids:
            return {"ok": False, "error": "missing attachment_ids"}
        k = max(1, min(20, int(top_k or 5)))
        mode_norm = str(mode or "keyword").strip().lower()
        if mode_norm not in {"keyword", "hybrid"}:
            mode_norm = "keyword"

        docs = list(
            db.scalars(
                select(AttachmentDocument).where(
                    AttachmentDocument.user_id == int(user_id),
                    AttachmentDocument.workspace == workspace_norm,
                    AttachmentDocument.id.in_(ids),
                    AttachmentDocument.parse_status == "ready",
                )
            )
        )
        if not docs:
            return {"ok": True, "content": "", "hits": [], "total": 0, "attachment_ids": []}

        allowed_ids = {int(row.id) for row in docs}
        doc_map = {int(row.id): row for row in docs}
        candidate_limit = max(120, min(400, k * 40))
        query_lower = q.lower()[:200]
        token_terms: list[str] = []
        for token in self._tokenize(q):
            if not token:
                continue
            if token in token_terms:
                continue
            token_terms.append(token)
            if len(token_terms) >= 8:
                break

        lexical_filters = [
            AttachmentChunk.text.ilike(f"%{escape_sql_like(term)}%", escape="\\")
            for term in token_terms
        ]
        if query_lower:
            lexical_filters.append(AttachmentChunk.text.ilike(f"%{escape_sql_like(query_lower)}%", escape="\\"))

        chunk_stmt = select(AttachmentChunk).where(AttachmentChunk.attachment_id.in_(allowed_ids))
        if lexical_filters:
            chunk_stmt = chunk_stmt.where(or_(*lexical_filters))
        chunk_stmt = chunk_stmt.order_by(AttachmentChunk.id.desc()).limit(candidate_limit)
        chunks = list(db.scalars(chunk_stmt))
        if not chunks:
            chunks = list(
                db.scalars(
                    select(AttachmentChunk)
                    .where(AttachmentChunk.attachment_id.in_(allowed_ids))
                    .order_by(AttachmentChunk.id.desc())
                    .limit(candidate_limit)
                )
            )
        if not chunks:
            return {"ok": True, "content": "", "hits": [], "total": 0, "attachment_ids": sorted(allowed_ids)}

        tokens = self._tokenize(q)
        token_counter = Counter(tokens)
        phrase = q.lower()
        query_norm = math.sqrt(sum(v * v for v in token_counter.values())) or 1.0

        scored: list[tuple[float, AttachmentChunk]] = []
        for chunk in chunks:
            text = str(chunk.text or "")
            if not text:
                continue
            lowered = text.lower()
            lexical = float(sum(lowered.count(token) for token in token_counter if token))
            if phrase and phrase in lowered:
                lexical += 3.0
            score = lexical
            if mode_norm == "hybrid":
                row_vec = self._safe_load_json(str(chunk.keyword_vector_json or "{}"))
                dot = 0.0
                row_sq = 0.0
                for term, weight in row_vec.items():
                    try:
                        w = float(weight)
                    except Exception:
                        continue
                    row_sq += w * w
                    dot += w * float(token_counter.get(str(term), 0))
                if row_sq > 0:
                    score += dot / (math.sqrt(row_sq) * query_norm)
            if score <= 0:
                continue
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            fallback_chunks = sorted(
                chunks,
                key=lambda row: (int(row.attachment_id), int(row.chunk_index), int(row.id)),
            )
            for chunk in fallback_chunks[: max(k * 2, k)]:
                scored.append((0.0001, chunk))

        hits: list[dict[str, Any]] = []
        seen_texts: set[str] = set()
        for score, chunk in scored:
            normalized = self._norm_text(str(chunk.text or ""))
            if not normalized:
                continue
            dedupe_key = normalized[:180]
            if dedupe_key in seen_texts:
                continue
            seen_texts.add(dedupe_key)
            doc = doc_map.get(int(chunk.attachment_id))
            if doc is None:
                continue
            loc = self._safe_load_json(str(chunk.loc_json or "{}"))
            citation = {
                "attachment_id": int(doc.id),
                "file_name": str(doc.file_name or ""),
                "page": int(loc.get("page") or 0) or None,
                "slide": int(loc.get("slide") or 0) or None,
                "sheet": str(loc.get("sheet") or "") or None,
                "row_range": (f"{loc.get('row')}" if loc.get("row") else None),
            }
            hits.append(
                {
                    "chunk_id": int(chunk.id),
                    "text": normalized[:1400],
                    "score": round(float(score), 4),
                    "citation": citation,
                    "metadata": {
                        "attachment_id": int(doc.id),
                        "workspace": str(doc.workspace or ""),
                        "loc": loc,
                    },
                }
            )
            if len(hits) >= k:
                break

        content_lines = [f"[{idx + 1}] {hit['text']}" for idx, hit in enumerate(hits)]
        return {
            "ok": True,
            "content": "\n\n".join(content_lines)[:8000],
            "hits": hits,
            "total": len(hits),
            "attachment_ids": sorted(allowed_ids),
        }

_ATTACHMENT_SERVICE_SINGLETON: AelinAttachmentService | None = None
_ATTACHMENT_SERVICE_LOCK = threading.Lock()


def get_aelin_attachment_service() -> AelinAttachmentService:
    global _ATTACHMENT_SERVICE_SINGLETON
    if _ATTACHMENT_SERVICE_SINGLETON is None:
        with _ATTACHMENT_SERVICE_LOCK:
            if _ATTACHMENT_SERVICE_SINGLETON is None:
                _ATTACHMENT_SERVICE_SINGLETON = AelinAttachmentService()
    return _ATTACHMENT_SERVICE_SINGLETON
