# Copyright (c) 2026 Lekkalu
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

import app.core.models  # noqa: F401  (register tables on Base.metadata)
import app.customers.models  # noqa: F401
import app.ledger.models  # noqa: F401
import app.messaging.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base

config = context.config
if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# Tests pass the test database URL through attributes; everything else uses DATABASE_URL.
url = config.attributes.get("url") or get_settings().database_url

engine = create_engine(url)
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
