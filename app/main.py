# Copyright (c) 2026 Lekkalu
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core import database
from app.core.logging import setup_logging

setup_logging()
log = logging.getLogger(__name__)
app = FastAPI(title="Lekkalu")


@app.get("/health")
def health():
    try:
        with database.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.exception("health check failed")
        return JSONResponse({"status": "degraded", "db": "error"}, status_code=503)
    return {"status": "ok", "db": "ok"}
