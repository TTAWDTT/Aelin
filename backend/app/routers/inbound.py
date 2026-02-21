from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud import create_message, touch_account_sync, touch_contact_last_message
from app.db import get_session
from app.models import ConnectedAccount, Contact, ForwardAccountConfig
from app.services import content_tagging
from app.services.forwarding import parse_forward_recipient, verify_forward_signature
from app.services.summarizer import RuleBasedSummarizer

router = APIRouter(prefix="/inbound", tags=["inbound"])
_HTML_TAG_RE = re.compile(r"<[^>]+>")


class ForwardInboundPayload(BaseModel):
    sender: str = Field(min_length=1, max_length=255)
    subject: str = Field(default="", max_length=998)
    body: str = Field(default="", max_length=20000)
    external_id: str | None = Field(default=None, max_length=255)
    received_at: datetime | None = None


def _clean_sender(value: str | None) -> str:
    if not value:
        return ""
    parsed = parseaddr(value)[1] or value
    return parsed.strip()


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _extract_message_body(message) -> str:
    if not message.is_multipart():
        content = message.get_content()
        if isinstance(content, str):
            if message.get_content_type() == "text/html":
                return " ".join(_HTML_TAG_RE.sub(" ", content).split())
            return content.strip()
        return ""

    for part in message.walk():
        if part.get_content_type() != "text/plain":
            continue
        payload = part.get_content()
        if isinstance(payload, str) and payload.strip():
            return payload.strip()

    for part in message.walk():
        if part.get_content_type() != "text/html":
            continue
        payload = part.get_content()
        if isinstance(payload, str) and payload.strip():
            return " ".join(_HTML_TAG_RE.sub(" ", payload).split())
    return ""


def _parse_raw_email(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw.encode("utf-8", errors="ignore"))
    except Exception:
        return {}
    return {
        "sender": message.get("from"),
        "recipient": message.get("to") or message.get("delivered-to"),
        "subject": message.get("subject"),
        "body": _extract_message_body(message),
        "external_id": message.get("message-id"),
        "received_at": _coerce_datetime(message.get("date")),
    }


def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _find_account_by_forward_recipient(db: Session, recipients: list[str]) -> ConnectedAccount | None:
    for recipient in recipients:
        parsed = parse_forward_recipient(recipient)
        if parsed is None:
            continue
        account_id, signature = parsed
        config = db.get(ForwardAccountConfig, account_id)
        if config is None:
            continue
        if not verify_forward_signature(
            account_id=account_id,
            inbound_secret=config.inbound_secret,
            signature=signature,
        ):
            continue
        account = db.get(ConnectedAccount, config.account_id)
        if account is None or account.provider.lower() != "forward":
            continue
        return account
    return None


def _ingest_forward_message(
    db: Session,
    *,
    account: ConnectedAccount,
    sender: str,
    subject: str,
    body: str,
    external_id: str | None,
    received_at: datetime | None,
) -> None:
    summarizer = RuleBasedSummarizer()
    normalized_sender = sender.strip() or "forward@unknown.local"
    contact = db.scalar(
        select(Contact).where(Contact.user_id == account.user_id, Contact.handle == normalized_sender)
    )
    if contact is None:
        contact = Contact(user_id=account.user_id, handle=normalized_sender, display_name=normalized_sender)
        db.add(contact)
        db.flush()

    received_at_utc = received_at.astimezone(timezone.utc) if received_at else datetime.now(timezone.utc)
    external_id_norm = external_id.strip() if external_id else ""
    if not external_id_norm:
        digest = sha256(
            f"{account.id}|{normalized_sender}|{subject}|{received_at_utc.isoformat()}".encode("utf-8")
        ).hexdigest()
        external_id = f"forward:{digest[:32]}"
    else:
        external_id = external_id_norm

    msg = create_message(
        db,
        user_id=account.user_id,
        contact_id=contact.id,
        source="email",
        external_id=external_id,
        sender=normalized_sender,
        subject=subject,
        body=body,
        received_at=received_at_utc,
        summary=summarizer.summarize(body),
        skip_external_id_check=False,
    )
    tagged_message_ids: list[int] = []
    if msg is not None:
        if getattr(msg, "id", None) is None:
            db.flush()
        tagged_message_ids.append(int(msg.id))
        touch_contact_last_message(db, contact=contact, received_at=received_at_utc)
    touch_account_sync(db, account=account)
    db.commit()
    if tagged_message_ids:
        content_tagging.enqueue_tagging_job(
            user_id=account.user_id,
            message_ids=tagged_message_ids,
            allow_llm=True,
        )


@router.post("/forward/{secret}")
def receive_forward(
    secret: str,
    payload: ForwardInboundPayload,
    db: Session = Depends(get_session),
):
    config = db.scalar(select(ForwardAccountConfig).where(ForwardAccountConfig.inbound_secret == secret))
    if config is None:
        raise HTTPException(status_code=404, detail="Forward secret not found")
    account = db.get(ConnectedAccount, config.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    _ingest_forward_message(
        db,
        account=account,
        sender=payload.sender,
        subject=payload.subject,
        body=payload.body,
        external_id=payload.external_id,
        received_at=payload.received_at,
    )
    return {"ok": True, "account_id": account.id}


@router.post("/forward")
async def receive_forward_by_address(
    request: Request,
    db: Session = Depends(get_session),
):
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload_raw = await request.json()
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form_data = await request.form()
        payload_raw = {}
        for key, value in form_data.multi_items():
            if isinstance(value, str):
                payload_raw[key] = value
    else:
        body = await request.body()
        if not body:
            payload_raw = {}
        else:
            try:
                payload_raw = json.loads(body.decode("utf-8"))
            except Exception:
                payload_raw = {"raw": body.decode("utf-8", errors="ignore")}

    if not isinstance(payload_raw, dict):
        raise HTTPException(status_code=400, detail="Invalid inbound payload")

    payload = {str(key).lower(): value for key, value in payload_raw.items()}

    raw_email = _first_text(payload, "raw", "raw_email", "mime", "email")
    raw_fields = _parse_raw_email(raw_email)

    recipient_candidates: list[str] = []
    for key in (
        "recipient",
        "to",
        "envelope_to",
        "delivered_to",
        "x_original_to",
        "forward_to",
    ):
        candidate = _first_text(payload, key)
        if candidate:
            recipient_candidates.extend(part.strip() for part in re.split(r"[,;\n]+", candidate) if part.strip())
    for header in ("x-original-to", "delivered-to", "x-forwarded-to"):
        header_value = request.headers.get(header)
        if header_value:
            recipient_candidates.extend(part.strip() for part in re.split(r"[,;\n]+", header_value) if part.strip())
    raw_recipient = raw_fields.get("recipient")
    if isinstance(raw_recipient, str) and raw_recipient.strip():
        recipient_candidates.extend(part.strip() for part in re.split(r"[,;\n]+", raw_recipient) if part.strip())

    account = _find_account_by_forward_recipient(db, recipient_candidates)
    if account is None:
        raise HTTPException(status_code=404, detail="Forward recipient not found")

    sender = _clean_sender(
        _first_text(payload, "sender", "from", "from_email", "mail_from")
        or (raw_fields.get("sender") if isinstance(raw_fields.get("sender"), str) else "")
    )
    subject = _first_text(payload, "subject", "title") or (
        raw_fields.get("subject") if isinstance(raw_fields.get("subject"), str) else ""
    )
    body = _first_text(
        payload,
        "body",
        "text",
        "plain",
        "textbody",
        "body-plain",
        "stripped-text",
        "htmlbody",
        "body-html",
        "html",
    )
    if not body:
        body = raw_fields.get("body") if isinstance(raw_fields.get("body"), str) else ""
    if not body:
        body = subject or "(转发邮件无正文)"

    external_id = _first_text(payload, "external_id", "message-id", "message_id", "messageid")
    if not external_id:
        raw_external_id = raw_fields.get("external_id")
        external_id = raw_external_id if isinstance(raw_external_id, str) else None

    received_at = _coerce_datetime(payload.get("received_at") or payload.get("date"))
    if received_at is None:
        raw_received = raw_fields.get("received_at")
        received_at = raw_received if isinstance(raw_received, datetime) else None

    _ingest_forward_message(
        db,
        account=account,
        sender=sender or account.identifier,
        subject=subject or "",
        body=body,
        external_id=external_id,
        received_at=received_at,
    )
    return {"ok": True, "account_id": account.id}
