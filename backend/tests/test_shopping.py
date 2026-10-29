"""Shopping list through the API and the service."""

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import ShoppingItem
from app.schemas import ShoppingItemIn
from app.services import pantry
from app.services import shopping as service
from tests.test_recipes import RECIPE, post_recipe

INGREDIENTS = [
	{"amount": "250", "unit": "g", "name": "Kürbis"},
	{"amount": "1", "unit": "Stück", "name": "Zwiebel",
	 "note": "gross"},
	{"amount": "0.5", "unit": "TL", "name": "Salz"},
	{"amount": "2", "unit": "EL", "name": "Olivenöl"},
	{"amount": None, "unit": "", "name": "Petersilie"},
]


def recipe_with(ingredients):
	data = copy.deepcopy(RECIPE)
	data["version"]["ingredients"] = ingredients
	return data


@pytest.fixture
def staples(db):
	for name in ("Salz", "Pfeffer", "Olivenöl", "Öl"):
		pantry.add_item(db, name)


@pytest.fixture
def recipe(auth_client, staples):
	return post_recipe(auth_client, recipe_with(INGREDIENTS))


def from_recipe(client, recipe_id, factor=None):
	body = {} if factor is None else {"factor": factor}
	return client.post(f"/api/shopping/from-recipe/{recipe_id}",
			   json=body)


def post_item(client, name, unit="", amount=None, note=""):
	resp = client.post("/api/shopping", json={
		"name": name, "unit": unit, "amount": amount, "note": note})
	assert resp.status_code == 201, resp.text
	return resp.json()


def lines(client):
	return [(i["name"], i["unit"], i["amount"], i["checked"])
		for i in client.get("/api/shopping").json()]


def test_from_recipe_skips_pantry(auth_client, recipe):
	resp = from_recipe(auth_client, recipe["id"])
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert [i["name"] for i in body] == ["Kürbis", "Zwiebel",
					     "Petersilie"]
	assert body[0]["amount"] == "250"
	assert body[0]["unit"] == "g"
	assert body[1]["note"] == "gross"
	assert body[2]["amount"] is None
	assert all(i["recipe_id"] == recipe["id"] for i in body)
	assert all(i["checked"] is False for i in body)
	assert set(body[0]) == {"id", "name", "unit", "amount", "note",
				"checked", "recipe_id"}
	assert len(auth_client.get("/api/shopping").json()) == 3


def test_from_recipe_factor(auth_client, recipe):
	body = from_recipe(auth_client, recipe["id"], "0.5").json()
	assert [i["amount"] for i in body] == ["125", "0.5", None]


@pytest.mark.parametrize("factor", ["0", "-1", "101"])
def test_from_recipe_bad_factor(auth_client, recipe, factor):
	assert from_recipe(auth_client, recipe["id"],
			   factor).status_code == 422


def test_from_recipe_twice_merges(auth_client, recipe):
	from_recipe(auth_client, recipe["id"])
	body = from_recipe(auth_client, recipe["id"], "2").json()
	assert [i["amount"] for i in body] == ["750", "3", None]
	assert lines(auth_client) == [
		("Kürbis", "g", "750", False),
		("Zwiebel", "Stück", "3", False),
		("Petersilie", "", None, False),
	]


def test_merge_ignores_case_and_unit_alias(auth_client, staples):
	post_item(auth_client, "kürbis", "Gramm", "100", "Hokkaido")
	recipe = post_recipe(auth_client, recipe_with(INGREDIENTS[:1]))
	body = from_recipe(auth_client, recipe["id"]).json()
	assert len(body) == 1
	assert body[0]["name"] == "kürbis"
	assert body[0]["unit"] == "Gramm"
	assert body[0]["amount"] == "350"
	assert body[0]["note"] == "Hokkaido"
	assert len(auth_client.get("/api/shopping").json()) == 1


def test_merge_keeps_amount_when_one_side_has_none(auth_client, staples):
	post_item(auth_client, "Kürbis", "g")
	recipe = post_recipe(auth_client, recipe_with(INGREDIENTS[:1]))
	body = from_recipe(auth_client, recipe["id"]).json()
	assert body[0]["amount"] == "250"
	assert len(auth_client.get("/api/shopping").json()) == 1


def test_merge_joins_different_notes(auth_client, staples):
	post_item(auth_client, "Zwiebel", "Stück", "2", "rot")
	recipe = post_recipe(auth_client, recipe_with(INGREDIENTS[1:2]))
	body = from_recipe(auth_client, recipe["id"]).json()
	assert body[0]["note"] == "rot; gross"
	assert body[0]["amount"] == "3"


def test_checked_items_are_not_merged_into(auth_client, recipe):
	first = from_recipe(auth_client, recipe["id"]).json()
	auth_client.put(f"/api/shopping/{first[0]['id']}/checked",
			json={"checked": True})
	body = from_recipe(auth_client, recipe["id"]).json()
	assert body[0]["id"] != first[0]["id"]
	assert body[0]["amount"] == "250"
	assert lines(auth_client) == [
		("Zwiebel", "Stück", "2", False),
		("Petersilie", "", None, False),
		("Kürbis", "g", "250", False),
		("Kürbis", "g", "250", True),
	]


def test_from_recipe_missing(auth_client):
	resp = from_recipe(auth_client, 9999)
	assert resp.status_code == 404
	assert resp.json() == {"detail": "recipe not found"}


def test_manual_add(auth_client):
	body = post_item(auth_client, "  Milch ", " l ", "1.50", " frisch ")
	assert body["name"] == "Milch"
	assert body["unit"] == "l"
	assert body["amount"] == "1.5"
	assert body["note"] == "frisch"
	assert body["checked"] is False
	assert body["recipe_id"] is None


@pytest.mark.parametrize("name", ["", "   "])
def test_manual_add_empty_name_rejected(auth_client, name):
	resp = auth_client.post("/api/shopping", json={"name": name})
	assert resp.status_code == 422


def test_update(auth_client):
	item = post_item(auth_client, "Milch", "l", "1")
	resp = auth_client.put(f"/api/shopping/{item['id']}", json={
		"name": "Hafermilch", "unit": "ml", "amount": "500",
		"note": "ungesüsst"})
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert body["id"] == item["id"]
	assert (body["name"], body["unit"], body["amount"], body["note"]) \
		== ("Hafermilch", "ml", "500", "ungesüsst")
	resp = auth_client.put("/api/shopping/9999", json={"name": "x"})
	assert resp.status_code == 404
	assert resp.json() == {"detail": "item not found"}


def test_check_uncheck_and_order(auth_client, db):
	a = post_item(auth_client, "A")
	b = post_item(auth_client, "B")
	c = post_item(auth_client, "C")
	old = datetime.now(timezone.utc) - timedelta(days=1)
	db.get(ShoppingItem, c["id"]).created_at = old
	db.commit()
	assert [n for n, *_ in lines(auth_client)] == ["C", "A", "B"]
	resp = auth_client.put(f"/api/shopping/{c['id']}/checked",
			       json={"checked": True})
	assert resp.status_code == 200
	assert resp.json()["checked"] is True
	assert [n for n, *_ in lines(auth_client)] == ["A", "B", "C"]
	auth_client.put(f"/api/shopping/{a['id']}/checked",
			json={"checked": True})
	assert [n for n, *_ in lines(auth_client)] == ["B", "C", "A"]
	auth_client.put(f"/api/shopping/{c['id']}/checked",
			json={"checked": False})
	assert [n for n, *_ in lines(auth_client)] == ["C", "B", "A"]
	assert b["id"] > 0
	resp = auth_client.put("/api/shopping/9999/checked",
			       json={"checked": True})
	assert resp.status_code == 404


def test_delete(auth_client, db):
	item = post_item(auth_client, "Milch")
	resp = auth_client.delete(f"/api/shopping/{item['id']}")
	assert resp.status_code == 204
	assert resp.content == b""
	assert db.get(ShoppingItem, item["id"]) is None
	resp = auth_client.delete(f"/api/shopping/{item['id']}")
	assert resp.status_code == 404
	assert resp.json() == {"detail": "item not found"}


def test_clear_checked(auth_client):
	a = post_item(auth_client, "A")
	post_item(auth_client, "B")
	c = post_item(auth_client, "C")
	for item in (a, c):
		auth_client.put(f"/api/shopping/{item['id']}/checked",
				json={"checked": True})
	resp = auth_client.delete("/api/shopping/checked")
	assert resp.status_code == 204
	assert lines(auth_client) == [("B", "", None, False)]
	assert auth_client.delete("/api/shopping/checked").status_code == 204
	assert len(lines(auth_client)) == 1


def test_service_merge_and_clear(db, auth_client, staples):
	recipe = post_recipe(auth_client, recipe_with(INGREDIENTS))
	assert service.add_from_recipe(db, 9999, Decimal(1)) is None
	items = service.add_from_recipe(db, recipe["id"], Decimal("0.333"))
	assert items[0].amount == Decimal("83.250")
	service.set_checked(db, items[0].id, True)
	assert service.clear_checked(db) == 1
	assert service.clear_checked(db) == 0
	item = service.add_item(db, ShoppingItemIn(name="Milch"))
	assert service.update_item(db, 9999, ShoppingItemIn(name="x")) \
		is None
	assert service.set_checked(db, 9999, True) is None
	assert service.delete_item(db, item.id) is True
	assert service.delete_item(db, item.id) is False


@pytest.mark.parametrize("text, expected", [
	("g", "g"), ("Gramm", "g"), (" GR ", "g"), ("EL", "EL"),
	("Esslöffel", "EL"), ("Stk", "Stück"), ("", ""), ("Prise", "Prise"),
	("Handvoll", "handvoll"),
])
def test_norm_unit(text, expected):
	assert service.norm_unit(text) == expected


def test_requires_login(client):
	assert client.get("/api/shopping").status_code == 401
	assert client.post("/api/shopping",
			   json={"name": "x"}).status_code == 401
	assert from_recipe(client, 1).status_code == 401
	assert client.put("/api/shopping/1",
			  json={"name": "x"}).status_code == 401
	assert client.put("/api/shopping/1/checked",
			  json={"checked": True}).status_code == 401
	assert client.delete("/api/shopping/1").status_code == 401
	assert client.delete("/api/shopping/checked").status_code == 401
