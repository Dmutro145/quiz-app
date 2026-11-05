import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Клієнт із чистою тимчасовою БД; питання завантажуються з data/*.csv при старті."""
    monkeypatch.setenv("QUIZ_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("TEACHER_PASSWORD", raising=False)
    monkeypatch.delenv("APPS_SCRIPT_URL", raising=False)
    from main import app

    with TestClient(app) as test_client:
        yield test_client
