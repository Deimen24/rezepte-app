"""List filters: q, category, tags, ingredients, favorite, combined."""

import pytest


def recipe(title, ingredients, tags=(), category_id=None,
	   favorite=False, intro=""):
	return {
		"category_id": category_id,
		"tags": list(tags),
		"favorite": favorite,
		"source": {"kind": "none"},
		"version": {
			"title": title,
			"intro": intro,
			"ingredients": [{"amount": "1", "unit": "",
					 "name": n} for n in ingredients],
			"steps": [{"text": "Kochen."}],
		},
	}


@pytest.fixture
def seeded(auth_client):
	"""Four recipes; returns a dict title -> id plus category ids."""
	c = auth_client
	suppen = c.post("/api/categories", json={"name": "Suppen"}).json()
	salate = c.post("/api/categories", json={"name": "Salate"}).json()
	data = [
		recipe("Kürbissuppe mit Feta", ["Kürbis", "Feta", "Zwiebel"],
		       tags=["vegi", "herbst"], category_id=suppen["id"],
		       favorite=True, intro="Cremig."),
		recipe("Kürbisrisotto", ["Kürbis", "Reis"],
		       tags=["vegi"], category_id=None,
		       intro="Mit Parmesan verfeinert."),
		recipe("Feta-Salat", ["Feta", "Gurke", "Tomate"],
		       tags=["vegi", "schnell"], category_id=salate["id"]),
		recipe("Bolognese", ["Hackfleisch", "Tomate"],
		       tags=["fleisch"], category_id=None, favorite=True,
		       intro="Klassiker aus der Toskana."),
	]
	ids = {}
	for d in data:
		resp = c.post("/api/recipes", json=d)
		assert resp.status_code == 201, resp.text
		ids[d["version"]["title"]] = resp.json()["id"]
	return {"ids": ids, "suppen": suppen["id"], "salate": salate["id"]}


def titles(client, params):
	resp = client.get("/api/recipes", params=params)
	assert resp.status_code == 200, resp.text
	return [r["title"] for r in resp.json()]


def test_list_all_ordered_by_title(auth_client, seeded):
	assert titles(auth_client, {}) == [
		"Bolognese", "Feta-Salat", "Kürbisrisotto",
		"Kürbissuppe mit Feta"]


def test_ingredients_and(auth_client, seeded):
	assert titles(auth_client, {"ingredients": "Kürbis,Feta"}) == [
		"Kürbissuppe mit Feta"]
	assert titles(auth_client, {"ingredients": "Kürbis"}) == [
		"Kürbisrisotto", "Kürbissuppe mit Feta"]
	assert titles(auth_client, {"ingredients": "Feta"}) == [
		"Feta-Salat", "Kürbissuppe mit Feta"]


def test_ingredients_partial_case_insensitive(auth_client, seeded):
	assert titles(auth_client, {"ingredients": "kürb"}) == [
		"Kürbisrisotto", "Kürbissuppe mit Feta"]
	assert titles(auth_client, {"ingredients": "FETA"}) == [
		"Feta-Salat", "Kürbissuppe mit Feta"]
	assert titles(auth_client, {"ingredients": "tomat, feta"}) == [
		"Feta-Salat"]
	assert titles(auth_client, {"ingredients": "Ananas"}) == []


def test_tags_and(auth_client, seeded):
	assert titles(auth_client, {"tags": "vegi"}) == [
		"Feta-Salat", "Kürbisrisotto", "Kürbissuppe mit Feta"]
	assert titles(auth_client, {"tags": "vegi,herbst"}) == [
		"Kürbissuppe mit Feta"]
	assert titles(auth_client, {"tags": "Vegi,SCHNELL"}) == [
		"Feta-Salat"]
	assert titles(auth_client, {"tags": "vegi,fleisch"}) == []


def test_category(auth_client, seeded):
	assert titles(auth_client, {"category": seeded["suppen"]}) == [
		"Kürbissuppe mit Feta"]
	assert titles(auth_client, {"category": seeded["salate"]}) == [
		"Feta-Salat"]
	assert titles(auth_client, {"category": 9999}) == []


def test_q_title_and_intro(auth_client, seeded):
	assert titles(auth_client, {"q": "kürbis"}) == [
		"Kürbisrisotto", "Kürbissuppe mit Feta"]
	assert titles(auth_client, {"q": "parmesan"}) == ["Kürbisrisotto"]
	assert titles(auth_client, {"q": "Toskana"}) == ["Bolognese"]
	assert titles(auth_client, {"q": "xyz"}) == []


def test_q_matches_own_title_after_update(auth_client, seeded):
	rid = seeded["ids"]["Bolognese"]
	body = recipe("Sugo", ["Hackfleisch", "Tomate"], favorite=True)
	resp = auth_client.put(f"/api/recipes/{rid}", json=body)
	assert resp.status_code == 200, resp.text
	assert titles(auth_client, {"q": "Sugo"}) == ["Sugo"]
	assert titles(auth_client, {"q": "Bolognese"}) == []


def test_favorite(auth_client, seeded):
	assert titles(auth_client, {"favorite": "true"}) == [
		"Bolognese", "Kürbissuppe mit Feta"]
	assert titles(auth_client, {"favorite": "false"}) == [
		"Feta-Salat", "Kürbisrisotto"]


def test_filters_combine(auth_client, seeded):
	assert titles(auth_client, {"tags": "vegi",
				    "favorite": "true"}) == [
		"Kürbissuppe mit Feta"]
	assert titles(auth_client, {"ingredients": "Tomate",
				    "tags": "vegi"}) == ["Feta-Salat"]
	assert titles(auth_client, {"q": "Kürbis",
				    "category": seeded["suppen"],
				    "ingredients": "feta"}) == [
		"Kürbissuppe mit Feta"]
	assert titles(auth_client, {"q": "Kürbis",
				    "category": seeded["salate"]}) == []
