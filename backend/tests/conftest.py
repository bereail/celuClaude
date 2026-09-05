"""Configuracion compartida de tests: variables de entorno de prueba
ANTES de importar la app (config.py las lee al importarse), una base de
datos SQLite temporal propia (nunca la command_center.db real), y un
fixture `client` que resetea el rate limiter de login entre tests.
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"ccc_test_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production"
os.environ["AGENT_ENROLLMENT_TOKEN"] = "test-enrollment-token"
os.environ["APP_USER_EMAIL"] = "test@example.com"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from passlib.context import CryptContext  # noqa: E402

TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "test-password-123"
os.environ["APP_USER_PASSWORD_HASH"] = CryptContext(schemes=["bcrypt"]).hash(TEST_PASSWORD)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import app  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402


@pytest.fixture
def client():
    auth_router._login_attempts.clear()
    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus):
    try:
        _TEST_DB_PATH.unlink(missing_ok=True)
    except OSError:
        pass  # sqlite en Windows puede seguir con el archivo abierto -- no es motivo para reportar la corrida como rota
