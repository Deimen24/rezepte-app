"""Recipe CRUD through the API."""

import copy

from app.models import Recipe, VersionKind

RECIPE = {
	"category_id": None,
	"tags": ["vegi", "Herbst"],
	"favorite": False,
	"source": {"kind": "url", "url": "https://example.org/kuerbis"},
	"version": {
		"title": "Kürbissuppe",
		"intro": "Cremig und wärmend.",
		"servings": 4,
		"prep_minutes": 15,
		"cook_minutes": 30,
		"ingredients": [
			{"amount": "250", "unit": "g", "name": "Kürbis",
			 "note": ""},
			{"amount": 0.5, "unit": "TL", "name": "Salz"},
			{"amount": None, "unit": "", "name": "Pfeffer",
			 "note": "nach Belieben"},
		],
		"steps": [{"text": "Kürbis würfeln."},
			  {"text": "Alles kochen."}],
	},
}


def post_recipe(client, data=RECIPE):
	resp = client.post("/api/recipes", json=data)
	assert resp.status_code == 201, resp.text
	return resp.json()


def test_create_recipe_both_versions_equal(auth_client):
	body = post_recipe(auth_client)
	assert body["id"] > 0
	assert body["original"] == body["own"]
	own = body["own"]
	assert own["title"] == "Kürbissuppe"
	assert own["servings"] == 4
	amounts = [i["amount"] for i in own["ingredients"]]
	assert amounts == ["250", "0.5", None]
	assert own["ingredients"][1]["note"] == ""
	assert [s["text"] for s in own["steps"]] == [
		"Kürbis würfeln.", "Alles kochen."]
	assert body["tags"] == ["Herbst", "vegi"]
	assert body["category"] is None
	assert body["source"]["kind"] == "url"
	assert body["source"]["url"] == "https://example.org/kuerbis"
	assert body["created_at"] and body["updated_at"]


def test_amount_trailing_zeros_stripped(auth_client):
	data = copy.deepcopy(RECIPE)
	data["version"]["ingredients"] = [
		{"amount": "1.500", "unit": "kg", "name": "Mehl"},
		{"amount": "2.000", "unit": "", "name": "Eier"},
	]
	body = post_recipe(auth_client, data)
	amounts = [i["amount"] for i in body["own"]["ingredients"]]
	assert amounts == ["1.5", "2"]


def test_get_recipe(auth_client):
	created = post_recipe(auth_client)
	resp = auth_client.get(f"/api/recipes/{created['id']}")
	assert resp.status_code == 200
	assert resp.json() == created


def test_get_missing_recipe(auth_client):
	resp = auth_client.get("/api/recipes/9999")
	assert resp.status_code == 404
	assert resp.json() == {"detail": "recipe not found"}


def test_list_shows_own_title(auth_client):
	created = post_recipe(auth_client)
	update = copy.deepcopy(RECIPE)
	update["version"]["title"] = "Meine Kürbissuppe"
	resp = auth_client.put(f"/api/recipes/{created['id']}", json=update)
	assert resp.status_code == 200, resp.text
	resp = auth_client.get("/api/recipes")
	assert resp.status_code == 200
	items = resp.json()
	assert len(items) == 1
	item = items[0]
	assert item["title"] == "Meine Kürbissuppe"
	assert set(item) == {"id", "title", "category", "tags",
			     "favorite", "thumb_url", "cooked_count",
			     "last_cooked", "updated_at"}
	assert item["tags"] == ["Herbst", "vegi"]


def test_update_changes_own_not_original(auth_client, db):
	created = post_recipe(auth_client)
	update = copy.deepcopy(RECIPE)
	update["version"]["title"] = "Kürbissuppe scharf"
	update["version"]["intro"] = "Mit Chili."
	update["version"]["servings"] = 2
	update["version"]["ingredients"] = [
		{"amount": "300", "unit": "g", "name": "Kürbis"},
		{"amount": "1", "unit": "", "name": "Chili"},
	]
	update["version"]["steps"] = [{"text": "Alles mit Chili kochen."}]
	resp = auth_client.put(f"/api/recipes/{created['id']}", json=update)
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert body["original"] == created["original"]
	own = body["own"]
	assert own["title"] == "Kürbissuppe scharf"
	assert own["intro"] == "Mit Chili."
	assert own["servings"] == 2
	assert [i["name"] for i in own["ingredients"]] == ["Kürbis",
							    "Chili"]
	assert [i["amount"] for i in own["ingredients"]] == ["300", "1"]
	assert [s["text"] for s in own["steps"]] == [
		"Alles mit Chili kochen."]
	assert own != body["original"]

	recipe = db.get(Recipe, created["id"])
	db.refresh(recipe)
	orig = recipe.version(VersionKind.ORIGINAL)
	assert orig.title == "Kürbissuppe"
	assert [i.name for i in orig.ingredients] == ["Kürbis", "Salz",
						       "Pfeffer"]
	assert len(orig.steps) == 2
	assert len(recipe.versions) == 2


def test_update_replaces_tags_category_and_meta(auth_client):
	resp = auth_client.post("/api/categories", json={"name": "Suppen"})
	assert resp.status_code == 201, resp.text
	cat = resp.json()
	created = post_recipe(auth_client)
	update = copy.deepcopy(RECIPE)
	update["category_id"] = cat["id"]
	update["tags"] = ["schnell"]
	update["favorite"] = True
	update["source"] = {"kind": "book", "book": "Tiptopf", "page": "42"}
	resp = auth_client.put(f"/api/recipes/{created['id']}", json=update)
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert body["category"] == {"id": cat["id"], "name": "Suppen"}
	assert body["tags"] == ["schnell"]
	assert body["favorite"] is True
	assert body["source"] == {"kind": "book", "url": None,
				  "book": "Tiptopf", "page": "42"}
	resp = auth_client.get("/api/tags")
	names = [t["name"] for t in resp.json()]
	assert "schnell" in names


def test_update_missing_recipe(auth_client):
	resp = auth_client.put("/api/recipes/9999", json=RECIPE)
	assert resp.status_code == 404


def test_update_unknown_category(auth_client):
	created = post_recipe(auth_client)
	update = copy.deepcopy(RECIPE)
	update["category_id"] = 12345
	resp = auth_client.put(f"/api/recipes/{created['id']}", json=update)
	assert resp.status_code == 422


def test_delete_recipe(auth_client):
	created = post_recipe(auth_client)
	resp = auth_client.delete(f"/api/recipes/{created['id']}")
	assert resp.status_code == 204
	resp = auth_client.get(f"/api/recipes/{created['id']}")
	assert resp.status_code == 404
	resp = auth_client.delete(f"/api/recipes/{created['id']}")
	assert resp.status_code == 404
	assert auth_client.get("/api/recipes").json() == []


def test_requires_login(client):
	assert client.get("/api/recipes").status_code == 401
	assert client.post("/api/recipes", json=RECIPE).status_code == 401
	assert client.get("/api/recipes/1").status_code == 401
	assert client.put("/api/recipes/1", json=RECIPE).status_code == 401
	assert client.delete("/api/recipes/1").status_code == 401
	assert client.get("/api/categories").status_code == 401
	assert client.get("/api/tags").status_code == 401


def test_empty_title_rejected(auth_client):
	data = copy.deepcopy(RECIPE)
	data["version"]["title"] = "   "
	resp = auth_client.post("/api/recipes", json=data)
	assert resp.status_code == 422
	del data["version"]["title"]
	resp = auth_client.post("/api/recipes", json=data)
	assert resp.status_code == 422


def test_source_url_without_url_rejected(auth_client):
	data = copy.deepcopy(RECIPE)
	data["source"] = {"kind": "url"}
	resp = auth_client.post("/api/recipes", json=data)
	assert resp.status_code == 422
	data["source"] = {"kind": "book", "page": "3"}
	resp = auth_client.post("/api/recipes", json=data)
	assert resp.status_code == 422
	data["source"] = {"kind": "none"}
	resp = auth_client.post("/api/recipes", json=data)
	assert resp.status_code == 201


def test_categories_and_tags_dedupe(auth_client):
	a = auth_client.post("/api/categories", json={"name": " Suppen "})
	b = auth_client.post("/api/categories", json={"name": "suppen"})
	assert a.status_code == 201 and b.status_code == 201
	assert a.json() == b.json()
	assert a.json()["name"] == "Suppen"
	resp = auth_client.post("/api/categories", json={"name": " "})
	assert resp.status_code == 422
	t1 = auth_client.post("/api/tags", json={"name": "Vegi"})
	t2 = auth_client.post("/api/tags", json={"name": "vegi"})
	assert t1.json() == t2.json()
	assert len(auth_client.get("/api/tags").json()) == 1
