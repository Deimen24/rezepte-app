"""Session cookie attributes and server-side session checks."""

import pytest
from sqlalchemy import delete, func, select

from app import auth
from app.config import settings
from app.models import Session, User
from app.routers.auth import SECONDS_PER_DAY
from app.services import auth as auth_service
from tests.conftest import TEST_PASSWORD, TEST_USER

LOGIN = "/api/auth/login"
LOGOUT = "/api/auth/logout"
ME = "/api/auth/me"
CREDENTIALS = {"username": TEST_USER, "password": TEST_PASSWORD}

RECIPE_BODY = {"version": {"title": "Brot"}}


def cookie_attrs(resp) -> dict:
	"""Parse the single Set-Cookie header into {attr_lower: value}."""
	header = resp.headers.get_list("set-cookie")
	assert len(header) == 1, header
	parts = [p.strip() for p in header[0].split(";")]
	attrs = {}
	for part in parts[1:]:
		key, _, value = part.partition("=")
		attrs[key.lower()] = value
	name, _, value = parts[0].partition("=")
	attrs["__name"] = name
	attrs["__value"] = value
	return attrs


def use_cookie(client, value):
	"""Replace the client's cookie jar with one session cookie.
	httpx deprecates per-request cookies, so set it on the client."""
	client.cookies.clear()
	client.cookies.set(auth.COOKIE_NAME, value)
	return client


def do_login(client, db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	resp = client.post(LOGIN, json=CREDENTIALS)
	assert resp.status_code == 200, resp.text
	return resp


def test_login_cookie_attributes(client, db):
	attrs = cookie_attrs(do_login(client, db))
	assert attrs["__name"] == auth.COOKIE_NAME
	assert len(attrs["__value"]) > 32
	assert "httponly" in attrs
	assert attrs["samesite"] == "lax"
	assert attrs["path"] == "/"
	assert attrs["max-age"] == str(settings.session_days
				       * SECONDS_PER_DAY)
	# conftest sets COOKIE_SECURE=false so the test client (http)
	# sends the cookie back; Secure must then be absent.
	assert settings.cookie_secure is False
	assert "secure" not in attrs


def test_secure_flag_follows_settings(client, db, monkeypatch):
	monkeypatch.setattr(settings, "cookie_secure", True)
	attrs = cookie_attrs(do_login(client, db))
	assert "secure" in attrs
	assert "httponly" in attrs


def test_cookie_value_is_not_the_stored_token_hash(client, db):
	token = cookie_attrs(do_login(client, db))["__value"]
	stored = db.scalar(select(Session.token_hash))
	assert stored != token
	assert stored == auth.hash_token(token)


def test_garbage_cookie_rejected(client, db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	for bad in ("garbage", "", "a" * 43, auth.new_token()):
		use_cookie(client, bad)
		assert client.get(ME).status_code == 401, bad
		assert client.get("/api/recipes").status_code == 401, bad


def test_tampered_cookie_rejected(client, db):
	token = cookie_attrs(do_login(client, db))["__value"]
	flipped = ("A" if token[0] != "A" else "B") + token[1:]
	assert use_cookie(client, flipped).get(ME).status_code == 401
	assert use_cookie(client, token).get(ME).status_code == 200


def test_session_of_deleted_user_rejected(client, db):
	do_login(client, db)
	assert client.get(ME).status_code == 200
	# Plain SQL delete so only the database cascade can act.
	db.execute(delete(User).where(User.username == TEST_USER))
	db.commit()
	assert client.get(ME).status_code == 401
	assert db.scalar(select(func.count()).select_from(Session)) == 0


def test_logout_invalidates_token_server_side(client, db):
	token = cookie_attrs(do_login(client, db))["__value"]
	resp = client.post(LOGOUT)
	assert resp.status_code == 200
	cleared = cookie_attrs(resp)
	assert cleared["max-age"] == "0"
	assert cleared["__value"] in ('""', "")
	assert db.scalars(select(Session)).all() == []
	assert use_cookie(client, token).get(ME).status_code == 401


def test_logout_only_ends_the_current_session(client, db):
	first = cookie_attrs(do_login(client, db))["__value"]
	second = client.post(LOGIN, json=CREDENTIALS)
	assert second.status_code == 200
	second_token = cookie_attrs(second)["__value"]
	use_cookie(client, second_token).post(LOGOUT)
	assert use_cookie(client, second_token).get(ME).status_code == 401
	assert use_cookie(client, first).get(ME).status_code == 200


def test_wrong_password_creates_no_session(client, db):
	auth_service.create_user(db, TEST_USER, TEST_PASSWORD)
	resp = client.post(LOGIN, json={"username": TEST_USER,
					"password": "nope"})
	assert resp.status_code == 401
	assert "set-cookie" not in resp.headers
	assert db.scalars(select(Session)).all() == []


@pytest.mark.parametrize("method, path, body", [
	("GET", "/api/recipes", None),
	("POST", "/api/recipes", RECIPE_BODY),
	("GET", "/api/recipes/1", None),
	("PUT", "/api/recipes/1", RECIPE_BODY),
	("DELETE", "/api/recipes/1", None),
	("GET", "/api/categories", None),
	("POST", "/api/categories", {"name": "x"}),
	("GET", "/api/tags", None),
	("POST", "/api/tags", {"name": "x"}),
	("GET", "/api/auth/me", None),
])
def test_endpoints_reject_requests_without_cookie(client, method, path,
						  body):
	resp = client.request(method, path, json=body)
	assert resp.status_code == 401
	assert resp.json() == {"detail": "not logged in"}


@pytest.mark.parametrize("method, path", [
	("POST", "/api/recipes"),
	("PUT", "/api/recipes/1"),
	("POST", "/api/categories"),
])
def test_login_is_checked_before_body_validation(client, method, path):
	resp = client.request(method, path, json={})
	assert resp.status_code == 401


def test_health_needs_no_cookie_and_sets_none(client):
	resp = client.get("/api/health")
	assert resp.status_code == 200
	assert "set-cookie" not in resp.headers
