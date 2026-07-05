from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.db.config import get_database_url


DATABASE_URL = get_database_url()

engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    # In-memory SQLite databases live for the lifetime of a single
    # connection. The TestClient serves requests from a worker thread, so
    # without a shared connection the test setup and the request handlers
    # would see different (empty) databases. StaticPool keeps one shared
    # connection so schema and data created in tests stay visible.
    if ":memory:" in DATABASE_URL or DATABASE_URL in ("sqlite://", "sqlite:///:memory:"):
        engine_kwargs["poolclass"] = StaticPool

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


class Base(DeclarativeBase):
    pass
