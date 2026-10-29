"""Pantry through the API and the service, including the match rule."""

import pytest

from app.models import PantryItem
from app.services import pantry as service

DEFAULTS = ("Salz", "Pfeffer", "Olivenöl", "Öl", "Wasser")


@pytest.fixture
def seeded(db):
	"""The migration seeds the defaults; create_all does not."""
	for name in DEFAULTS:
		service.add_item(db, name)
	return db


def test_list_sorted_case_insensitive(auth_client, db):
	for name in ("zimt", "Salz", "pfeffer", "Butter", "Essig"):
		service.add_item(db, name)
	body = auth_client.get("/api/pantry").json()
	names = [p["name"] for p in body]
	assert names == ["Butter", "Essig", "pfeffer", "Salz", "zimt"]
	assert set(body[0]) == {"id", "name"}


def test_add_trims_and_dedupes(auth_client, db):
	resp = auth_client.post("/api/pantry", json={"name": "  Mehl  "})
	assert resp.status_code == 201, resp.text
	first = resp.json()
	assert first["name"] == "Mehl"
	resp = auth_client.post("/api/pantry", json={"name": "MEHL"})
	assert resp.status_code == 201
	assert resp.json() == first
	assert len(auth_client.get("/api/pantry").json()) == 1


@pytest.mark.parametrize("name", ["", "   "])
def test_add_empty_rejected(auth_client, name):
	resp = auth_client.post("/api/pantry", json={"name": name})
	assert resp.status_code == 422


def test_delete(auth_client, db):
	item_id = auth_client.post("/api/pantry",
				   json={"name": "Zucker"}).json()["id"]
	resp = auth_client.delete(f"/api/pantry/{item_id}")
	assert resp.status_code == 204
	assert resp.content == b""
	assert db.get(PantryItem, item_id) is None
	resp = auth_client.delete(f"/api/pantry/{item_id}")
	assert resp.status_code == 404
	assert resp.json() == {"detail": "item not found"}


@pytest.mark.parametrize("name, expected", [
	("Salz", True),
	("salz", True),
	("  SALZ  ", True),
	("Öl zum Braten", True),
	("grobes Salz", True),
	("Olivenöl", True),
	("Rapsöl", False),
	("Salzkartoffeln", False),
	("Kürbis", False),
	("", False),
])
def test_is_pantry(seeded, name, expected):
	assert service.is_pantry(seeded, name) is expected


def test_service_add_and_remove(db):
	with pytest.raises(ValueError):
		service.add_item(db, "  ")
	item = service.add_item(db, " Mehl ")
	assert item.name == "Mehl"
	assert service.add_item(db, "mehl") is item
	assert service.remove_item(db, item.id) is True
	assert service.remove_item(db, item.id) is False


def test_requires_login(client):
	assert client.get("/api/pantry").status_code == 401
	assert client.post("/api/pantry",
			   json={"name": "x"}).status_code == 401
	assert client.delete("/api/pantry/1").status_code == 401
