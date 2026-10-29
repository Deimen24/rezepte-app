"""Favorite flag through the API and the service."""

import copy
from datetime import datetime

import pytest

from app.models import Recipe
from app.services import favorite as service
from tests.test_recipes import RECIPE, post_recipe


def put_favorite(client, recipe_id, body):
	return client.put(f"/api/recipes/{recipe_id}/favorite", json=body)


def list_ids(client, **params):
	resp = client.get("/api/recipes", params=params)
	assert resp.status_code == 200, resp.text
	return [r["id"] for r in resp.json()]


def test_round_trip(auth_client):
	recipe = post_recipe(auth_client)
	assert recipe["favorite"] is False
	resp = put_favorite(auth_client, recipe["id"], {"favorite": True})
	assert resp.status_code == 200, resp.text
	assert resp.json() == {"favorite": True}
	body = auth_client.get(f"/api/recipes/{recipe['id']}").json()
	assert body["favorite"] is True
	resp = put_favorite(auth_client, recipe["id"], {"favorite": False})
	assert resp.status_code == 200
	assert resp.json() == {"favorite": False}
	body = auth_client.get(f"/api/recipes/{recipe['id']}").json()
	assert body["favorite"] is False


def test_visible_in_list_filter(auth_client):
	a = post_recipe(auth_client)
	other = copy.deepcopy(RECIPE)
	other["version"]["title"] = "Apfelkuchen"
	b = post_recipe(auth_client, other)
	put_favorite(auth_client, a["id"], {"favorite": True})
	assert list_ids(auth_client, favorite="true") == [a["id"]]
	assert list_ids(auth_client, favorite="false") == [b["id"]]
	assert set(list_ids(auth_client)) == {a["id"], b["id"]}
	rows = {r["id"]: r for r in
		auth_client.get("/api/recipes").json()}
	assert rows[a["id"]]["favorite"] is True
	assert rows[b["id"]]["favorite"] is False


def test_updated_at_bumped(auth_client, db):
	recipe = post_recipe(auth_client)
	before = db.get(Recipe, recipe["id"]).updated_at
	db.execute(Recipe.__table__.update()
		   .where(Recipe.id == recipe["id"])
		   .values(updated_at=datetime(2000, 1, 1)))
	db.commit()
	put_favorite(auth_client, recipe["id"], {"favorite": True})
	after = db.get(Recipe, recipe["id"]).updated_at
	assert after.year > 2000
	assert after >= before.replace(tzinfo=after.tzinfo)


def test_missing_recipe(auth_client):
	resp = put_favorite(auth_client, 9999, {"favorite": True})
	assert resp.status_code == 404
	assert resp.json() == {"detail": "recipe not found"}


def test_requires_login(client):
	assert put_favorite(client, 1, {"favorite": True}).status_code == 401


@pytest.mark.parametrize("body", [None, {}, {"favorite": None},
				  {"favorite": "ja"}])
def test_invalid_body(auth_client, body):
	recipe = post_recipe(auth_client)
	resp = put_favorite(auth_client, recipe["id"], body)
	assert resp.status_code == 422


def test_service(db, auth_client):
	recipe = post_recipe(auth_client)
	assert service.set_favorite(db, 9999, True) is None
	row = service.set_favorite(db, recipe["id"], True)
	assert row.favorite is True
	assert db.get(Recipe, recipe["id"]).favorite is True
	assert service.set_favorite(db, recipe["id"], False).favorite is False
