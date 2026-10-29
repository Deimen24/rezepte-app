"""Public sharing: token handling, public view, photo delivery, leaks."""

import pytest

from app.config import settings
from app.models import TOKEN_LEN
from tests.test_photos import jpeg, upload
from tests.test_recipes import post_recipe

SHARED_KEYS = {"title", "category", "tags", "own", "photos"}
PRIVATE_KEYS = {"notes", "original", "source", "cook_log", "id",
		"favorite", "share_token"}
TOKEN_MIN = 40


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
	root = tmp_path / "media"
	monkeypatch.setattr(settings, "media_dir", str(root))
	return root


def share_url(recipe_id: int) -> str:
	return f"/api/recipes/{recipe_id}/share"


def enable(client, recipe_id: int) -> dict:
	resp = client.post(share_url(recipe_id))
	assert resp.status_code == 200, resp.text
	return resp.json()


def public(client, token: str):
	client.cookies.clear()
	return client.get(f"/api/share/{token}")


def test_enable_returns_token_and_path(auth_client):
	recipe = post_recipe(auth_client)
	body = enable(auth_client, recipe["id"])
	token = body["token"]
	assert set(body) == {"token", "path"}
	assert TOKEN_MIN <= len(token) <= TOKEN_LEN
	assert token.replace("-", "").replace("_", "").isalnum()
	assert body["path"] == f"/#/s/{token}"


def test_enable_is_idempotent(auth_client):
	recipe = post_recipe(auth_client)
	first = enable(auth_client, recipe["id"])
	second = enable(auth_client, recipe["id"])
	assert first == second
	state = auth_client.get(share_url(recipe["id"])).json()
	assert state == first


def test_state_is_off_by_default(auth_client):
	recipe = post_recipe(auth_client)
	resp = auth_client.get(share_url(recipe["id"]))
	assert resp.status_code == 200
	assert resp.json() == {"token": None, "path": None}


def test_token_never_in_recipe_out(auth_client):
	recipe = post_recipe(auth_client)
	token = enable(auth_client, recipe["id"])["token"]
	body = auth_client.get(f"/api/recipes/{recipe['id']}").json()
	assert "share_token" not in body
	assert token not in auth_client.get(
		f"/api/recipes/{recipe['id']}").text
	assert token not in auth_client.get("/api/recipes").text


def test_public_view_has_own_version_only(auth_client):
	recipe = post_recipe(auth_client)
	token = enable(auth_client, recipe["id"])["token"]
	resp = public(auth_client, token)
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert set(body) == SHARED_KEYS
	assert not PRIVATE_KEYS & set(body)
	assert body["title"] == recipe["own"]["title"]
	assert body["own"] == recipe["own"]
	assert body["tags"] == recipe["tags"]
	assert body["category"] == (recipe["category"] or {}).get("name")
	assert body["photos"] == []
	assert "set-cookie" not in resp.headers


def test_public_photo_urls_resolve_without_login(auth_client, media_dir):
	recipe = post_recipe(auth_client)
	pid = upload(auth_client, recipe["id"], jpeg()).json()["id"]
	token = enable(auth_client, recipe["id"])["token"]
	body = public(auth_client, token).json()
	assert body["photos"] == [f"/share/{token}/photos/{pid}.jpg"]
	resp = auth_client.get(body["photos"][0])
	assert resp.status_code == 200
	assert resp.headers["content-type"] == "image/jpeg"
	assert "set-cookie" not in resp.headers
	assert resp.content[:2] == b"\xff\xd8"


def test_disable_hides_view_and_photos(auth_client, media_dir):
	recipe = post_recipe(auth_client)
	pid = upload(auth_client, recipe["id"], jpeg()).json()["id"]
	token = enable(auth_client, recipe["id"])["token"]
	resp = auth_client.delete(share_url(recipe["id"]))
	assert resp.status_code == 200
	assert resp.json() == {"token": None, "path": None}
	assert auth_client.get(share_url(recipe["id"])).json() == {
		"token": None, "path": None}
	resp = public(auth_client, token)
	assert resp.status_code == 404
	assert resp.json() == {"detail": "not found"}
	assert auth_client.get(
		f"/share/{token}/photos/{pid}.jpg").status_code == 404


def test_wrong_token_is_404(auth_client, media_dir):
	recipe = post_recipe(auth_client)
	pid = upload(auth_client, recipe["id"], jpeg()).json()["id"]
	token = enable(auth_client, recipe["id"])["token"]
	wrong = ("A" if token[0] != "A" else "B") + token[1:]
	assert public(auth_client, wrong).status_code == 404
	assert public(auth_client, "").status_code == 404
	assert auth_client.get(
		f"/share/{wrong}/photos/{pid}.jpg").status_code == 404


def test_photo_of_other_recipe_is_404(auth_client, media_dir):
	shared = post_recipe(auth_client)
	other = post_recipe(auth_client)
	other_pid = upload(auth_client, other["id"], jpeg()).json()["id"]
	token = enable(auth_client, shared["id"])["token"]
	auth_client.cookies.clear()
	resp = auth_client.get(f"/share/{token}/photos/{other_pid}.jpg")
	assert resp.status_code == 404
	assert public(auth_client, token).json()["photos"] == []


def test_toggle_needs_login(client):
	for method in ("POST", "DELETE", "GET"):
		resp = client.request(method, share_url(1))
		assert resp.status_code == 401, method
		assert resp.json() == {"detail": "not logged in"}


def test_toggle_unknown_recipe_is_404(auth_client):
	for method in ("POST", "DELETE", "GET"):
		assert auth_client.request(method,
					   share_url(999)).status_code == 404


def test_share_gone_after_recipe_delete(auth_client, media_dir):
	recipe = post_recipe(auth_client)
	pid = upload(auth_client, recipe["id"], jpeg()).json()["id"]
	token = enable(auth_client, recipe["id"])["token"]
	assert auth_client.delete(
		f"/api/recipes/{recipe['id']}").status_code == 204
	assert auth_client.get(share_url(recipe["id"])).status_code == 404
	assert public(auth_client, token).status_code == 404
	assert auth_client.get(
		f"/share/{token}/photos/{pid}.jpg").status_code == 404
