"""Shared fixtures: SQLite in-memory database and API clients."""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
	sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["COOKIE_SECURE"] = "false"
os.environ.setdefault("MEDIA_DIR", "/tmp/rezepte-test-media")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base
from app.services import auth as auth_service

TEST_USER = "test"
TEST_PASSWORD = "secret"


def _sqlite_fk(conn, record):
	cur = conn.cursor()
	cur.execute("PRAGMA foreign_keys=ON")
	cur.close()


@pytest.fixture
def db():
	engine = create_engine("sqlite:///:memory:",
			       connect_args={"check_same_thread": False},
			       poolclass=StaticPool)
	event.listen(engine, "connect", _sqlite_fk)
	Base.metadata.create_all(engine)
	session = Session(engine, expire_on_commit=False)
	try:
		yield session
	finally:
		session.close()
		engine.dispose()


@pytest.fixture
def client(db):
	def override_db():
		yield db

	app.dependency_overrides[get_db] = override_db
	with TestClient(app) as c:
		yield c
	app.dependency_overrides.clear()


@pytest.fixture
def auth_client(client, db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	resp = client.post("/api/auth/login",
			   json={"username": TEST_USER,
				 "password": TEST_PASSWORD})
	assert resp.status_code == 200, resp.text
	return client
