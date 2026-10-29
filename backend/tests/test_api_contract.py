"""JSON shapes the frontend relies on (docs/PLAN.md, "JSON-Formen")."""

import importlib
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app import storage
from app.config import settings
from app.models import CookLog, Note, Photo

RECIPE_OUT_KEYS = {"id", "category", "tags", "favorite", "source",
		   "original", "own", "notes", "cook_log", "photos",
		   "created_at", "updated_at"}
LIST_ITEM_KEYS = {"id", "title", "category", "tags", "favorite",
		  "thumb_url", "cooked_count", "last_cooked", "updated_at"}
NOTE_KEYS = {"id", "created_at", "text"}
COOK_LOG_KEYS = {"id", "cooked_on", "rating", "comment"}
PHOTO_KEYS = {"id", "url", "thumb_url", "is_own_result", "created_at"}
VERSION_KEYS = {"title", "intro", "servings", "prep_minutes", "nutrition",
		"cook_minutes", "ingredients", "steps"}
INGREDIENT_KEYS = {"amount", "unit", "name", "note"}
STEP_KEYS = {"text"}
SOURCE_KEYS = {"kind", "url", "book", "page"}
CATEGORY_KEYS = {"id", "name"}

FULL = {
	"category_id": None,
	"tags": ["vegi"],
	"favorite": True,
	"source": {"kind": "book", "book": "Tiptopf", "page": "42"},
	"version": {
		"title": "Kürbissuppe",
		"intro": "Cremig.",
		"servings": 4,
		"prep_minutes": 15,
		"cook_minutes": 30,
		"ingredients": [
			{"amount": "250", "unit": "g", "name": "Kürbis"},
			{"amount": 0.5, "unit": "TL", "name": "Salz"},
			{"amount": None, "unit": "", "name": "Pfeffer"},
		],
		"steps": [{"text": "Kochen."}],
	},
}

MINIMAL = {"version": {"title": "Brot"}}


@pytest.fixture
def created(auth_client):
	resp = auth_client.post("/api/recipes", json=FULL)
	assert resp.status_code == 201, resp.text
	return resp.json()


@pytest.fixture
def minimal(auth_client):
	resp = auth_client.post("/api/recipes", json=MINIMAL)
	assert resp.status_code == 201, resp.text
	return resp.json()


def is_iso_datetime(text) -> bool:
	return isinstance(text, str) and \
		datetime.fromisoformat(text) is not None


def test_recipe_out_has_exactly_the_planned_keys(auth_client, created):
	resp = auth_client.get("/api/recipes/%d" % created["id"])
	body = resp.json()
	assert set(body) == RECIPE_OUT_KEYS
	for kind in ("original", "own"):
		assert set(body[kind]) == VERSION_KEYS
		for ing in body[kind]["ingredients"]:
			assert set(ing) == INGREDIENT_KEYS
		for step in body[kind]["steps"]:
			assert set(step) == STEP_KEYS
	assert set(body["source"]) == SOURCE_KEYS


def test_recipe_out_lists_are_empty_for_a_new_recipe(created):
	assert created["notes"] == []
	assert created["cook_log"] == []
	assert created["photos"] == []


def test_note_cook_log_photo_keys(auth_client, db, created):
	rid = created["id"]
	db.add(Note(recipe_id=rid, text="Mehr Salz."))
	db.add(CookLog(recipe_id=rid, cooked_on=date(2026, 10, 1),
		       rating=4, comment=""))
	photo = Photo(recipe_id=rid, filename="")
	db.add(photo)
	db.flush()
	photo.filename = storage.photo_name(photo.id)
	db.commit()
	body = auth_client.get("/api/recipes/%d" % rid).json()
	assert set(body["notes"][0]) == NOTE_KEYS
	assert set(body["cook_log"][0]) == COOK_LOG_KEYS
	assert set(body["photos"][0]) == PHOTO_KEYS
	photo = body["photos"][0]
	assert photo["url"] == "/media/%d.jpg" % photo["id"]
	assert photo["thumb_url"] == "/media/%d_t.jpg" % photo["id"]
	assert is_iso_datetime(photo["created_at"])
	assert is_iso_datetime(body["notes"][0]["created_at"])
	assert body["cook_log"][0]["cooked_on"] == "2026-10-01"


def test_post_and_put_return_the_same_shape_as_get(auth_client, created):
	got = auth_client.get("/api/recipes/%d" % created["id"]).json()
	assert set(created) == set(got) == RECIPE_OUT_KEYS
	put = auth_client.put("/api/recipes/%d" % created["id"], json=FULL)
	assert put.status_code == 200, put.text
	assert set(put.json()) == RECIPE_OUT_KEYS


def test_list_item_has_exactly_the_planned_keys(auth_client, created):
	items = auth_client.get("/api/recipes").json()
	assert len(items) == 1
	assert set(items[0]) == LIST_ITEM_KEYS
	assert items[0]["id"] == created["id"]
	assert items[0]["title"] == created["own"]["title"]
	assert items[0]["thumb_url"] is None
	assert items[0]["cooked_count"] == 0
	assert items[0]["last_cooked"] is None


def test_amounts_are_strings_or_null(created):
	amounts = [i["amount"] for i in created["own"]["ingredients"]]
	assert amounts == ["250", "0.5", None]
	for value in amounts:
		assert value is None or isinstance(value, str)


def test_source_always_has_all_four_keys(created, minimal):
	assert created["source"] == {"kind": "book", "url": None,
				     "book": "Tiptopf", "page": "42"}
	assert minimal["source"] == {"kind": "none", "url": None,
				     "book": None, "page": None}


def test_minimal_recipe_fills_defaults(minimal):
	own = minimal["own"]
	assert own["intro"] == ""
	assert own["servings"] is None
	assert own["prep_minutes"] is None
	assert own["cook_minutes"] is None
	assert own["ingredients"] == []
	assert own["steps"] == []
	assert minimal["tags"] == []
	assert minimal["favorite"] is False
	assert minimal["category"] is None


def test_category_is_null_or_id_name_object(auth_client, minimal):
	assert minimal["category"] is None
	cat = auth_client.post("/api/categories",
			       json={"name": "Brot"}).json()
	data = dict(MINIMAL, category_id=cat["id"])
	resp = auth_client.put("/api/recipes/%d" % minimal["id"], json=data)
	body = resp.json()
	assert set(body["category"]) == CATEGORY_KEYS
	assert body["category"] == cat
	item = auth_client.get("/api/recipes").json()[0]
	assert item["category"] == cat


def test_dates_are_iso_strings(auth_client, created):
	assert is_iso_datetime(created["created_at"])
	assert is_iso_datetime(created["updated_at"])
	item = auth_client.get("/api/recipes").json()[0]
	assert is_iso_datetime(item["updated_at"])


def test_scalar_types_match_plan(created):
	assert isinstance(created["id"], int)
	assert isinstance(created["favorite"], bool)
	assert all(isinstance(t, str) for t in created["tags"])
	own = created["own"]
	assert isinstance(own["servings"], int)
	assert isinstance(own["ingredients"][0]["unit"], str)
	assert isinstance(own["ingredients"][0]["note"], str)


def test_validation_error_has_detail_list(auth_client):
	resp = auth_client.post("/api/recipes", json={"version": {}})
	assert resp.status_code == 422
	body = resp.json()
	assert set(body) == {"detail"}
	assert isinstance(body["detail"], list)
	assert body["detail"][0]["loc"][-1] == "title"


def test_not_found_and_not_logged_in_use_detail_string(client,
							auth_client):
	resp = auth_client.get("/api/recipes/9999")
	assert resp.json() == {"detail": "recipe not found"}
	auth_client.cookies.clear()
	resp = client.get("/api/recipes")
	assert resp.json() == {"detail": "not logged in"}


def test_openapi_and_docs_disabled_by_default(client):
	assert settings.api_docs is False
	assert client.get("/api/openapi.json").status_code == 404
	assert client.get("/api/docs").status_code == 404


def test_openapi_and_docs_enabled_by_setting(monkeypatch):
	"""main.py builds the app at import time, so a fresh app needs a
	module reload; the module is reloaded again with the original
	setting so later tests see the default app."""
	monkeypatch.setattr(settings, "api_docs", True)
	try:
		fresh = importlib.reload(main_module).app
		with TestClient(fresh) as c:
			spec = c.get("/api/openapi.json")
			assert spec.status_code == 200
			paths = spec.json()["paths"]
			assert "/api/recipes/{recipe_id}" in paths
			assert c.get("/api/docs").status_code == 200
	finally:
		monkeypatch.undo()
		importlib.reload(main_module)
	assert main_module.app.openapi_url is None
