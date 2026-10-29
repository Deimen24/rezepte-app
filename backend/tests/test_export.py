"""GET /api/export: ZIP with recipes.json and the stored photo files."""

import io
import json
import re
import zipfile
from datetime import date

import pytest

from app import storage
from app.config import settings
from app.models import CookLog, Note, Photo
from app.schemas import RecipeOut

FILENAME_RE = re.compile(
	r'^attachment; filename="rezepte-\d{8}-\d{4}\.zip"$')
JPEG = b"\xff\xd8\xff\xe0fake"


def recipe(title, tag):
	return {"tags": [tag], "source": {"kind": "none"},
		"version": {"title": title, "steps": [{"text": "Kochen."}]}}


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
	monkeypatch.setattr(settings, "media_dir", str(tmp_path))
	return tmp_path


@pytest.fixture
def seeded(auth_client, db, media_dir):
	"""Two recipes; the first has a photo with files, the second a
	photo row whose files are missing."""
	c = auth_client
	c.post("/api/categories", json={"name": "Suppen"})
	a = c.post("/api/recipes", json=recipe("Suppe", "vegi")).json()
	b = c.post("/api/recipes", json=recipe("Brot", "backen")).json()
	db.add(Note(recipe_id=a["id"], text="Mehr Salz."))
	db.add(CookLog(recipe_id=a["id"], cooked_on=date(2026, 10, 1),
		       rating=4, comment="Gut."))
	stored = Photo(recipe_id=a["id"], filename="x.jpg")
	missing = Photo(recipe_id=b["id"], filename="y.jpg")
	db.add_all([stored, missing])
	db.commit()
	storage.save(storage.photo_name(stored.id), JPEG)
	storage.save(storage.photo_name(stored.id, thumb=True), JPEG)
	return {"a": a["id"], "b": b["id"], "stored": stored.id,
		"missing": missing.id}


def fetch_zip(client):
	resp = client.get("/api/export")
	assert resp.status_code == 200, resp.text
	assert resp.headers["content-type"] == "application/zip"
	assert FILENAME_RE.match(resp.headers["content-disposition"])
	return zipfile.ZipFile(io.BytesIO(resp.content))


def test_export_requires_login(client):
	assert client.get("/api/export").status_code == 401


def test_export_json_shape(auth_client, seeded):
	zf = fetch_zip(auth_client)
	data = json.loads(zf.read("recipes.json"))
	assert set(data) == {"exported_at", "version", "categories",
			     "tags", "recipes"}
	assert data["version"] == 1
	assert [c["name"] for c in data["categories"]] == ["Suppen"]
	assert sorted(t["name"] for t in data["tags"]) == ["backen",
							   "vegi"]
	assert [r["id"] for r in data["recipes"]] == [seeded["a"],
						      seeded["b"]]
	for r in data["recipes"]:
		assert set(r) == set(RecipeOut.model_fields)
	first = data["recipes"][0]
	assert first["notes"][0]["text"] == "Mehr Salz."
	assert first["cook_log"][0]["cooked_on"] == "2026-10-01"
	assert first["photos"][0]["id"] == seeded["stored"]


def test_export_photos_only_existing_files(auth_client, seeded):
	zf = fetch_zip(auth_client)
	names = set(zf.namelist())
	stored = storage.photo_name(seeded["stored"])
	thumb = storage.photo_name(seeded["stored"], thumb=True)
	assert "photos/" + stored in names
	assert "photos/" + thumb in names
	assert "photos/" + storage.photo_name(seeded["missing"]) not in names
	assert zf.read("photos/" + stored) == JPEG
	assert zf.getinfo("photos/" + stored).compress_type == \
		zipfile.ZIP_STORED
	assert zf.getinfo("recipes.json").compress_type == \
		zipfile.ZIP_DEFLATED


def test_build_zip_stats(db, seeded):
	from app.services import export
	_data, stats = export.build_zip(db)
	assert stats == {"recipes": 2, "photos": 2, "missing": 2}


def test_export_empty_database(auth_client):
	zf = fetch_zip(auth_client)
	data = json.loads(zf.read("recipes.json"))
	assert data["recipes"] == []
	assert zf.namelist() == ["recipes.json"]
