import os

from app.core.env import load_env


def get_database_url() -> str:
    """Return the configured database URL, failing closed if it is absent."""

    load_env()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Create a .env file from .env.example or export DATABASE_URL."
        )
    return database_url
