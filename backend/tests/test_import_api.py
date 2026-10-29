"""Import endpoints: preview, ingredient parsing, photo from URL and
the round trip preview -> POST /api/recipes."""

from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import settings
from app.importer import fetch
from app.importer.fetch import FetchError
from app.models import Photo, Recipe
from app.services import importer as service

PAGE_URL = "https://example.com/rezepte/suppe"

JSONLD_PAGE = """<!doctype html>
<html><head><title>Seite</title>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Recipe",
 "name": "K\\u00fcrbissuppe", "description": "Herbstlich.",
 "recipeYield": "4 Portionen", "prepTime": "PT15M", "cookTime": "PT30M",
 "recipeIngredient": ["500 g K\\u00fcrbis", "1 Zwiebel", "2 EL Oliven\\u00f6l"],
 "recipeInstructions": [
  {"@type": "HowToStep", "text": "K\\u00fcrbis w\\u00fcrfeln."},
  {"@type": "HowToStep", "text": "Alles weich kochen."}],
 "image": "/bilder/suppe.jpg"}
</script></head><body><h1>Egal</h1></body></html>
"""

HEURISTIC_PAGE = """<!doctype html>
<html><head><title>Pancakes</title></head><body>
<h1>Pancakes</h1>
<ul><li>200 g Mehl</li><li>2 Eier</li><li>300 ml Milch</li></ul>
</body></html>
"""

EMPTY_PAGE = "<!doctype html><html><body><p>Hallo</p></body></html>"

PREVIEW_KEYS = {"source", "version", "image_url", "method", "warnings"}


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
	root = tmp_path / "media"
	monkeypatch.setattr(settings, "media_dir", str(root))
	return root


def serve(monkeypatch, html: str, final_url: str = PAGE_URL):
	monkeypatch.setattr(service, "fetch_html",
			    lambda url, client=None: (html, final_url))


def recipe_count(db) -> int:
	return len(list(db.scalars(select(Recipe))))


def jpeg() -> bytes:
	buf = BytesIO()
	Image.new("RGB", (640, 480), (200, 50, 50)).save(buf, "JPEG")
	return buf.getvalue()


def test_fetch_jsonld_preview(auth_client, db, monkeypatch):
	serve(monkeypatch, JSONLD_PAGE)
	before = recipe_count(db)
	resp = auth_client.post("/api/import/fetch",
				json={"url": "https://example.com/x"})
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert set(body) == PREVIEW_KEYS
	assert body["method"] == "jsonld"
	assert body["source"] == {"kind": "url", "url": PAGE_URL,
				  "book": None, "page": None}
	version = body["version"]
	assert version["title"] == "Kürbissuppe"
	assert version["intro"] == "Herbstlich."
	assert version["servings"] == 4
	assert version["prep_minutes"] == 15
	assert version["cook_minutes"] == 30
	raws = [i["raw"] for i in version["ingredients"]]
	assert raws == ["500 g Kürbis", "1 Zwiebel", "2 EL Olivenöl"]
	for item in version["ingredients"]:
		assert set(item) == {"amount", "unit", "name", "note", "raw"}
		assert item["name"]
	assert [s["text"] for s in version["steps"]] == [
		"Kürbis würfeln.", "Alles weich kochen."]
	assert body["image_url"] == "https://example.com/bilder/suppe.jpg"
	assert body["warnings"] == []
	assert recipe_count(db) == before


def test_fetch_heuristic_preview_has_warnings(auth_client, monkeypatch):
	serve(monkeypatch, HEURISTIC_PAGE)
	resp = auth_client.post("/api/import/fetch",
				json={"url": "https://example.com/x"})
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert body["method"] == "heuristic"
	assert body["version"]["title"] == "Pancakes"
	assert len(body["version"]["ingredients"]) == 3
	assert body["version"]["steps"] == []
	assert "Keine Schritte" in body["warnings"]
	assert body["image_url"] is None


def test_fetch_page_without_recipe_is_422(auth_client, db, monkeypatch):
	serve(monkeypatch, EMPTY_PAGE)
	resp = auth_client.post("/api/import/fetch",
				json={"url": "https://example.com/x"})
	assert resp.status_code == 422
	assert resp.json() == {"detail": "Kein Rezept gefunden"}
	assert recipe_count(db) == 0


@pytest.mark.parametrize("url, detail", [
	("nicht-mal-eine-adresse", "Adresse ungültig"),
	("ftp://example.com/x", "Nur http und https"),
	("http://localhost/x", "Adresse nicht erlaubt"),
])
def test_fetch_invalid_url_is_422(auth_client, url, detail):
	resp = auth_client.post("/api/import/fetch", json={"url": url})
	assert resp.status_code == 422
	assert resp.json() == {"detail": detail}


def test_fetch_empty_url_is_422(auth_client):
	resp = auth_client.post("/api/import/fetch", json={"url": "  "})
	assert resp.status_code == 422


def test_fetch_requires_login(client):
	resp = client.post("/api/import/fetch",
			   json={"url": "https://example.com/x"})
	assert resp.status_code == 401


def test_parse_ingredients(auth_client):
	resp = auth_client.post("/api/import/ingredients", json={
		"lines": ["500 g Kürbis", "1 Zwiebel", "Salz"]})
	assert resp.status_code == 200, resp.text
	items = resp.json()
	assert len(items) == 3
	assert [i["raw"] for i in items] == ["500 g Kürbis", "1 Zwiebel",
					     "Salz"]
	assert items[0]["amount"] == "500"
	assert items[0]["unit"] == "g"
	assert items[0]["name"] == "Kürbis"
	assert items[2]["amount"] is None
	assert items[2]["name"] == "Salz"


def test_parse_ingredients_skips_blank_lines(auth_client):
	resp = auth_client.post("/api/import/ingredients", json={
		"lines": ["", "1 Ei", "   "]})
	assert resp.status_code == 200
	assert len(resp.json()) == 1


def test_parse_ingredients_too_many_lines(auth_client):
	resp = auth_client.post("/api/import/ingredients", json={
		"lines": ["1 Ei"] * 201})
	assert resp.status_code == 422


def test_parse_ingredients_requires_login(client):
	resp = client.post("/api/import/ingredients", json={"lines": ["x"]})
	assert resp.status_code == 401


def post_recipe(client) -> dict:
	resp = client.post("/api/recipes", json={
		"version": {"title": "Test", "ingredients": [], "steps": []}})
	assert resp.status_code == 201, resp.text
	return resp.json()


def test_photo_from_url(auth_client, db, media_dir, monkeypatch):
	seen = []

	def fake_image(url, client=None):
		seen.append(url)
		return jpeg()

	monkeypatch.setattr(fetch, "fetch_image", fake_image)
	recipe = post_recipe(auth_client)
	resp = auth_client.post(f"/api/recipes/{recipe['id']}/photos/url",
				json={"url": "https://example.com/a.jpg"})
	assert resp.status_code == 201, resp.text
	body = resp.json()
	assert set(body) == {"id", "url", "thumb_url", "is_own_result",
			     "created_at"}
	assert body["is_own_result"] is False
	assert seen == ["https://example.com/a.jpg"]
	pid = body["id"]
	assert (media_dir / f"{pid}.jpg").is_file()
	assert (media_dir / f"{pid}_t.jpg").is_file()
	assert db.get(Photo, pid).recipe_id == recipe["id"]


def test_photo_from_url_not_an_image_is_415(auth_client, db, media_dir,
					    monkeypatch):
	monkeypatch.setattr(fetch, "fetch_image",
			    lambda url, client=None: b"<html>nope</html>")
	recipe = post_recipe(auth_client)
	resp = auth_client.post(f"/api/recipes/{recipe['id']}/photos/url",
				json={"url": "https://example.com/a.jpg"})
	assert resp.status_code == 415
	assert resp.json() == {"detail": "not an image"}
	assert list(db.scalars(select(Photo))) == []
	assert not media_dir.exists() or not any(media_dir.iterdir())


def test_photo_from_url_fetch_error_is_422(auth_client, db, media_dir,
					   monkeypatch):
	def fail(url, client=None):
		raise FetchError("Kein Bild")

	monkeypatch.setattr(fetch, "fetch_image", fail)
	recipe = post_recipe(auth_client)
	resp = auth_client.post(f"/api/recipes/{recipe['id']}/photos/url",
				json={"url": "https://example.com/a.txt"})
	assert resp.status_code == 422
	assert resp.json() == {"detail": "Kein Bild"}
	assert list(db.scalars(select(Photo))) == []


def test_photo_from_private_url_is_422_without_fetch(auth_client,
						     media_dir):
	recipe = post_recipe(auth_client)
	resp = auth_client.post(f"/api/recipes/{recipe['id']}/photos/url",
				json={"url": "http://127.0.0.1/a.jpg"})
	assert resp.status_code == 422
	assert resp.json() == {"detail": "Adresse nicht erlaubt"}


def test_photo_from_url_missing_recipe_is_404(auth_client, media_dir,
					      monkeypatch):
	def never(url, client=None):
		raise AssertionError("must not fetch")

	monkeypatch.setattr(fetch, "fetch_image", never)
	resp = auth_client.post("/api/recipes/9999/photos/url",
				json={"url": "https://example.com/a.jpg"})
	assert resp.status_code == 404
	assert resp.json() == {"detail": "recipe not found"}


def test_photo_from_url_requires_login(client, media_dir):
	resp = client.post("/api/recipes/1/photos/url",
			   json={"url": "https://example.com/a.jpg"})
	assert resp.status_code == 401


def without_raw(items: list[dict]) -> list[dict]:
	return [{k: v for k, v in i.items() if k != "raw"} for i in items]


def test_round_trip_preview_to_recipe(auth_client, monkeypatch):
	serve(monkeypatch, JSONLD_PAGE)
	preview = auth_client.post("/api/import/fetch",
				   json={"url": "https://example.com/x"}).json()
	version = dict(preview["version"])
	version["ingredients"] = without_raw(version["ingredients"])
	resp = auth_client.post("/api/recipes", json={
		"source": preview["source"], "version": version})
	assert resp.status_code == 201, resp.text
	saved = resp.json()
	original = saved["original"]
	assert original["title"] == preview["version"]["title"]
	assert original["ingredients"] == version["ingredients"]
	assert original["steps"] == preview["version"]["steps"]
	assert original["servings"] == preview["version"]["servings"]
	assert saved["source"] == preview["source"]
	assert saved["own"] == original
