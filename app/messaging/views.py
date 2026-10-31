# Copyright (c) 2026 Lekkalu
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.messaging import services
from app.processing import pipeline

router = APIRouter()
CHAT_PAGE = Path(__file__).parent / "static" / "chat.html"
Db = Annotated[Session, Depends(get_session)]
Token = Annotated[str | None, Header(alias="X-Access-Token")]


class NewMessage(BaseModel):
    client_message_id: UUID
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


def _business(session: Session, slug: str, token: str | None):
    b = services.resolve_business(session, slug, token)
    if b is None:
        raise HTTPException(404)  # same answer for unknown slug and wrong token
    return b


@router.get("/c/{slug}")
def chat_page(slug: str, session: Db, t: str | None = None):
    _business(session, slug, t)
    return FileResponse(CHAT_PAGE)


@router.post("/api/{slug}/messages", status_code=202)
def post_message(slug: str, body: NewMessage, background: BackgroundTasks, session: Db, token: Token = None):
    b = _business(session, slug, token)
    try:
        msg = services.store_message(session, business_id=b.id, client_message_id=str(body.client_message_id),
                                     text=body.text)
    except services.MessageConflict:
        raise HTTPException(409) from None
    session.commit()
    background.add_task(pipeline.process_business, b.id)  # a no-op when nothing is waiting
    return {"id": msg.id}


@router.get("/api/{slug}/messages")
def get_messages(slug: str, session: Db, token: Token = None, after: int | None = None):
    b = _business(session, slug, token)
    return [
        {"id": m.id, "client_message_id": m.external_message_id, "body": m.body, "status": m.status,
         "reply_text": m.reply_text}
        for m in services.list_messages(session, business_id=b.id, after=after)
    ]
