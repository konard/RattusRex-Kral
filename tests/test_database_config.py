import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.db.config import get_database_url


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("app.db.config.load_env", lambda: {})

    with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is not set"):
        get_database_url()


def test_database_url_uses_explicit_environment_value(monkeypatch):
    database_url = "sqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr("app.db.config.load_env", lambda: {})

    assert get_database_url() == database_url


def run_database_import(database_url_marker: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if database_url_marker is None:
        env.pop("DATABASE_URL", None)
    else:
        env["DATABASE_URL"] = database_url_marker

    script = """
import app.core.env

app.core.env.load_env = lambda *args, **kwargs: {}

try:
    import app.db.database as database
except RuntimeError as exc:
    print(str(exc))
    raise SystemExit(10)

print(database.DATABASE_URL)
"""
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )


def test_database_url_is_required_when_env_and_dotenv_are_missing():
    result = run_database_import(None)

    assert result.returncode == 10, result.stdout + result.stderr
    assert "DATABASE_URL environment variable is not set" in result.stdout


def test_database_url_from_environment_is_accepted():
    result = run_database_import("sqlite://")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "sqlite://"


def test_committed_files_do_not_contain_previous_database_password():
    previous_password = "Gal" + "U5TA1"

    result = subprocess.run(
        ["git", "grep", "-n", previous_password, "--", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 1, result.stdout
