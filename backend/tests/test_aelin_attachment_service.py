from __future__ import annotations

import io
import zipfile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import AttachmentChunk, AttachmentDocument, Base, User
from app.services.aelin_attachment_service import AelinAttachmentService
from app.settings import settings


def _create_db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return SessionLocal()


def _seed_user(db: Session, user_id: int = 1) -> None:
    db.add(User(id=user_id, email=f"user{user_id}@example.com", hashed_password="x"))
    db.commit()


def test_ingest_bytes_deduplicates(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "aelin_attachment_storage_dir", str(tmp_path / "attachments"))
    service = AelinAttachmentService()
    db = _create_db()
    _seed_user(db, user_id=1)

    first = service.ingest_bytes(
        db,
        user_id=1,
        workspace="default",
        session_id="s1",
        file_name="note.txt",
        mime_type="text/plain",
        content=b"alpha beta gamma",
    )
    db.commit()
    second = service.ingest_bytes(
        db,
        user_id=1,
        workspace="default",
        session_id="s1",
        file_name="note.txt",
        mime_type="text/plain",
        content=b"alpha beta gamma",
    )

    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert second["attachment_id"] == first["attachment_id"]
    assert db.query(AttachmentDocument).count() == 1
    assert db.query(AttachmentChunk).count() >= 1


def test_search_handles_like_wildcards(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "aelin_attachment_storage_dir", str(tmp_path / "attachments"))
    service = AelinAttachmentService()
    db = _create_db()
    _seed_user(db, user_id=7)

    doc = AttachmentDocument(
        user_id=7,
        workspace="default",
        session_id="s2",
        file_name="demo.txt",
        file_ext="txt",
        mime_type="text/plain",
        size_bytes=12,
        sha256="a" * 64,
        storage_path="demo",
        parse_status="ready",
        summary="demo",
        metadata_json="{}",
    )
    db.add(doc)
    db.flush()
    db.add(
        AttachmentChunk(
            attachment_id=int(doc.id),
            chunk_index=0,
            text="profit 100% and key_internal marker",
            token_count=6,
            keyword_vector_json='{"profit":1,"100":1,"internal":1}',
            loc_json='{"page":1}',
        )
    )
    db.commit()

    result = service.search(
        db,
        user_id=7,
        workspace="default",
        query="100% key_internal",
        attachment_ids=[int(doc.id)],
        top_k=5,
        mode="hybrid",
    )
    assert result["ok"] is True
    assert int(result["total"]) >= 1
    assert result["hits"][0]["citation"]["file_name"] == "demo.txt"


def test_parse_pptx_ignores_non_numeric_slide_names(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "aelin_attachment_storage_dir", str(tmp_path / "attachments"))
    service = AelinAttachmentService()

    buff = io.BytesIO()
    with zipfile.ZipFile(buff, mode="w") as zf:
        zf.writestr(
            "ppt/slides/slide1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                   xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Hello Slide</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
            </p:sld>""",
        )
        zf.writestr("ppt/slides/slideX.xml", "<bad/>")

    parsed_text, blocks, metadata = service._parse_pptx(buff.getvalue(), file_name="demo.pptx")
    assert "Hello Slide" in parsed_text
    assert any(block.block_type == "slide" for block in blocks)
    assert int(metadata["slide_count"]) == 1
