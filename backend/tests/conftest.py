"""Temporary isolated SQLite tests. PostgreSQL integration is run separately by CI."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from app.db import Base, get_db, new_engine
from app import db_models
from app.main import app
from app.auth import _attempts


@pytest.fixture
def api(tmp_path):
    engine = new_engine(f"sqlite:///{tmp_path/'test.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override
    _attempts.clear()
    with TestClient(app) as client:
        yield client, sessions
    app.dependency_overrides.clear()
    engine.dispose()


def register(client, email="alice@example.com", password="correct-horse-battery-123"):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    current = client.get("/api/auth/me")
    assert current.status_code == 200, current.text
    return current.json()
