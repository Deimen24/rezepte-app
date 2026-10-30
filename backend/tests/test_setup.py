"""First-use setup: the single user is created from the login screen."""

from sqlalchemy import select

from app.models import User
from app.services import auth as auth_service
from tests.conftest import TEST_PASSWORD, TEST_USER

STRONG = "mindestens-acht"


def test_setup_needed_on_empty_database(client):
	assert client.get("/api/auth/setup").json() == {"needed": True}


def test_setup_creates_user_and_logs_in(client, db):
	r = client.post("/api/auth/setup",
			json={"username": " anna ", "password": STRONG})
	assert r.status_code == 201
	assert r.json() == {"username": "anna"}
	assert "session" in r.cookies
	assert client.get("/api/auth/me").json() == {"username": "anna"}
	assert db.scalars(select(User.username)).all() == ["anna"]
	assert client.get("/api/auth/setup").json() == {"needed": False}


def test_setup_refused_once_a_user_exists(client, db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	r = client.post("/api/auth/setup",
			json={"username": "zwei", "password": STRONG})
	assert r.status_code == 409
	assert db.scalars(select(User.username)).all() == [TEST_USER]


def test_setup_rejects_short_password_and_empty_name(client, db):
	for body in ({"username": "anna", "password": "kurz"},
		     {"username": "  ", "password": STRONG},
		     {"username": "anna"}):
		assert client.post("/api/auth/setup", json=body).status_code == 422
	assert db.scalars(select(User)).all() == []


def test_setup_state_sets_no_cookie(client):
	r = client.get("/api/auth/setup")
	assert "set-cookie" not in r.headers
