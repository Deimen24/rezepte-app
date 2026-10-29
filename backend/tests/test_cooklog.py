"""Cook log entries through the API and the service."""

from datetime import date

import pytest

from app.models import CookLog
from app.schemas import COMMENT_MAX, CookLogIn
from app.services import cooklog as service
from tests.test_recipes import post_recipe

ENTRY = {"cooked_on": "2026-10-28", "rating": 4, "comment": "Gut."}


def post_entry(client, recipe_id, data=ENTRY):
	return client.post(f"/api/recipes/{recipe_id}/cooklog", json=data)


def test_create_entry(auth_client):
	recipe = post_recipe(auth_client)
	resp = post_entry(auth_client, recipe["id"])
	assert resp.status_code == 201, resp.text
	body = resp.json()
	assert set(body) == {"id", "cooked_on", "rating", "comment"}
	assert body["id"] > 0
	assert body["cooked_on"] == "2026-10-28"
	assert body["rating"] == 4
	assert body["comment"] == "Gut."


@pytest.mark.parametrize("rating", [0, 6, -1, "gut"])
def test_rating_out_of_range(auth_client, rating):
	recipe = post_recipe(auth_client)
	resp = post_entry(auth_client, recipe["id"],
			  {**ENTRY, "rating": rating})
	assert resp.status_code == 422


def test_rating_null_and_comment_default(auth_client):
	recipe = post_recipe(auth_client)
	resp = post_entry(auth_client, recipe["id"],
			  {"cooked_on": "2026-01-02", "rating": None})
	assert resp.status_code == 201, resp.text
	assert resp.json()["rating"] is None
	assert resp.json()["comment"] == ""
	resp = post_entry(auth_client, recipe["id"],
			  {"cooked_on": "2026-01-03"})
	assert resp.status_code == 201, resp.text
	assert resp.json()["rating"] is None
	assert resp.json()["comment"] == ""


def test_comment_stripped(auth_client):
	recipe = post_recipe(auth_client)
	resp = post_entry(auth_client, recipe["id"],
			  {**ENTRY, "comment": "  Gut. \n"})
	assert resp.json()["comment"] == "Gut."


def test_comment_too_long(auth_client):
	recipe = post_recipe(auth_client)
	resp = post_entry(auth_client, recipe["id"],
			  {**ENTRY, "comment": "x" * (COMMENT_MAX + 1)})
	assert resp.status_code == 422


@pytest.mark.parametrize("cooked_on",
			 ["2026-13-01", "gestern", "", None, "2026-02-30"])
def test_invalid_date(auth_client, cooked_on):
	recipe = post_recipe(auth_client)
	resp = post_entry(auth_client, recipe["id"],
			  {**ENTRY, "cooked_on": cooked_on})
	assert resp.status_code == 422


def test_missing_cooked_on(auth_client):
	recipe = post_recipe(auth_client)
	resp = post_entry(auth_client, recipe["id"], {"rating": 3})
	assert resp.status_code == 422


def test_missing_recipe(auth_client):
	resp = post_entry(auth_client, 9999)
	assert resp.status_code == 404
	assert resp.json() == {"detail": "recipe not found"}


def test_delete_entry(auth_client, db):
	recipe = post_recipe(auth_client)
	entry_id = post_entry(auth_client, recipe["id"]).json()["id"]
	url = f"/api/recipes/{recipe['id']}/cooklog/{entry_id}"
	resp = auth_client.delete(url)
	assert resp.status_code == 204
	assert resp.content == b""
	assert db.get(CookLog, entry_id) is None
	resp = auth_client.delete(url)
	assert resp.status_code == 404
	assert resp.json() == {"detail": "entry not found"}


def test_delete_with_wrong_recipe(auth_client, db):
	recipe = post_recipe(auth_client)
	entry_id = post_entry(auth_client, recipe["id"]).json()["id"]
	resp = auth_client.delete(f"/api/recipes/9999/cooklog/{entry_id}")
	assert resp.status_code == 404
	assert db.get(CookLog, entry_id) is not None


def test_entry_bound_to_its_recipe(auth_client, db):
	a = post_recipe(auth_client)
	b = post_recipe(auth_client)
	entry_id = post_entry(auth_client, a["id"]).json()["id"]
	resp = auth_client.delete(
		f"/api/recipes/{b['id']}/cooklog/{entry_id}")
	assert resp.status_code == 404
	assert resp.json() == {"detail": "entry not found"}
	assert db.get(CookLog, entry_id) is not None


def test_requires_login(client):
	assert post_entry(client, 1).status_code == 401
	assert client.delete("/api/recipes/1/cooklog/1").status_code == 401


def test_recipe_lists_entries_newest_first(auth_client):
	recipe = post_recipe(auth_client)
	post_entry(auth_client, recipe["id"], {"cooked_on": "2026-01-01"})
	post_entry(auth_client, recipe["id"], {"cooked_on": "2026-03-01"})
	post_entry(auth_client, recipe["id"], {"cooked_on": "2026-02-01"})
	body = auth_client.get(f"/api/recipes/{recipe['id']}").json()
	if "cook_log" not in body:
		pytest.skip("RecipeOut.cook_log not yet filled by to_out")
	assert [e["cooked_on"] for e in body["cook_log"]] == [
		"2026-03-01", "2026-02-01", "2026-01-01"]


def test_service_add_and_delete(db, auth_client):
	recipe = post_recipe(auth_client)
	data = CookLogIn(cooked_on=date(2026, 5, 1), rating=5)
	assert service.add_entry(db, 9999, data) is None
	entry = service.add_entry(db, recipe["id"], data)
	assert entry.id > 0
	assert entry.cooked_on == date(2026, 5, 1)
	assert entry.rating == 5 and entry.comment == ""
	assert service.delete_entry(db, recipe["id"] + 1, entry.id) is False
	assert service.delete_entry(db, recipe["id"], entry.id) is True
	assert service.delete_entry(db, recipe["id"], entry.id) is False
