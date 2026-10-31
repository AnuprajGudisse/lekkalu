# Copyright (c) 2026 Lekkalu
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core import database
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.messaging.views import router as messaging_router
from app.processing import pipeline

setup_logging()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not get_settings().meta_api_key:
        log.error("META_API_KEY is not set: every message will fail with the 'send again' reply")
    # Single worker: anything left `processing` was interrupted by a restart.
    for business_id in pipeline.recover():
        threading.Thread(target=pipeline.process_business, args=(business_id,), daemon=True).start()
    yield


app = FastAPI(title="Lekkalu", lifespan=lifespan)
app.include_router(messaging_router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "messaging" / "static"), name="static")


@app.get("/health")
def health():
    try:
        with database.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.exception("health check failed")
        return JSONResponse({"status": "degraded", "db": "error"}, status_code=503)
    return {"status": "ok", "db": "ok"}
