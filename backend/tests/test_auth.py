"""Login, logout, session expiry and the auth service."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import auth
from app.models import Session
from app.services import auth as auth_service
from tests.conftest import TEST_PASSWORD, TEST_USER

LOGIN = "/api/auth/login"
LOGOUT = "/api/auth/logout"
ME = "/api/auth/me"


def test_health_is_open(client):
	r = client.get("/api/health")
	assert r.status_code == 200
	assert r.json() == {"status": "ok"}


def test_me_requires_login(client):
	r = client.get(ME)
	assert r.status_code == 401
	assert r.json() == {"detail": "not logged in"}


def test_login_wrong_password(client, db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	r = client.post(LOGIN, json={"username": TEST_USER,
				     "password": "nope"})
	assert r.status_code == 401
	assert r.json() == {"detail": "wrong credentials"}
	assert auth.COOKIE_NAME not in r.cookies


def test_login_unknown_user(client):
	r = client.post(LOGIN, json={"username": "nobody",
				     "password": "x"})
	assert r.status_code == 401


def test_login_sets_cookie_and_me_works(client, db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	r = client.post(LOGIN, json={"username": TEST_USER,
				     "password": TEST_PASSWORD})
	assert r.status_code == 200
	assert r.json() == {"username": TEST_USER}
	assert auth.COOKIE_NAME in r.cookies
	header = r.headers["set-cookie"].lower()
	assert "httponly" in header
	assert "samesite=lax" in header
	assert "path=/" in header

	r = client.get(ME)
	assert r.status_code == 200
	assert r.json() == {"username": TEST_USER}


def test_auth_client_is_logged_in(auth_client):
	r = auth_client.get(ME)
	assert r.status_code == 200
	assert r.json()["username"] == TEST_USER


def test_logout(auth_client, db):
	r = auth_client.post(LOGOUT)
	assert r.status_code == 200
	assert r.json() == {"ok": True}
	assert auth_client.get(ME).status_code == 401
	assert db.scalars(select(Session)).all() == []


def test_logout_without_login(client):
	r = client.post(LOGOUT)
	assert r.status_code == 200
	assert r.json() == {"ok": True}


def test_expired_session_rejected(auth_client, db):
	sess = db.scalars(select(Session)).one()
	sess.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
	db.commit()
	assert auth_client.get(ME).status_code == 401


def test_purge_expired(db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	tok_old = auth_service.login(db, TEST_USER, TEST_PASSWORD)
	tok_new = auth_service.login(db, TEST_USER, TEST_PASSWORD)
	sess = db.scalar(select(Session)
			 .where(Session.token_hash == auth.hash_token(tok_old)))
	sess.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
	db.commit()
	assert auth_service.purge_expired(db) == 1
	assert auth_service.user_for_token(db, tok_old) is None
	assert auth_service.user_for_token(db, tok_new) is not None


def test_create_user_duplicate_raises(db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	with pytest.raises(ValueError):
		auth_service.create_user(db, TEST_USER, "other")


def test_set_password(db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	auth_service.set_password(db, TEST_USER, "changed")
	assert auth_service.login(db, TEST_USER, TEST_PASSWORD) is None
	assert auth_service.login(db, TEST_USER, "changed") is not None
	with pytest.raises(ValueError):
		auth_service.set_password(db, "nobody", "x")


def test_verify_password():
	h = auth.hash_password("secret")
	assert h != "secret"
	assert auth.verify_password(h, "secret")
	assert not auth.verify_password(h, "wrong")
	assert not auth.verify_password("garbage", "secret")


def test_token_helpers():
	t1, t2 = auth.new_token(), auth.new_token()
	assert t1 != t2
	assert len(auth.hash_token(t1)) == 64
	assert auth.hash_token(t1) == auth.hash_token(t1)
