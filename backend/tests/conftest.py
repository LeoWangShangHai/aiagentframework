import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# Ensure backend package imports resolve during test collection as well.
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app  # noqa: WPS433

    return fastapi_app


@pytest.fixture()
def client(app):
    return TestClient(app)
