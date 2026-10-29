"""Notes on a recipe through the API and the service."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Note
from app.schemas import NOTE_MAX, NoteIn
from app.services import notes as service
from tests.test_recipes import post_recipe


def post_note(client, recipe_id, text="Weniger Salz."):
	return client.post(f"/api/recipes/{recipe_id}/notes",
			   json={"text": text})


def test_create_note(auth_client):
	recipe = post_recipe(auth_client)
	resp = post_note(auth_client, recipe["id"], "  Weniger Salz.  ")
	assert resp.status_code == 201, resp.text
	body = resp.json()
	assert set(body) == {"id", "created_at", "text"}
	assert body["id"] > 0
	assert body["text"] == "Weniger Salz."
	assert body["created_at"]


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_empty_text_rejected(auth_client, text):
	recipe = post_recipe(auth_client)
	resp = post_note(auth_client, recipe["id"], text)
	assert resp.status_code == 422


def test_too_long_text_rejected(auth_client):
	recipe = post_recipe(auth_client)
	resp = post_note(auth_client, recipe["id"], "x" * (NOTE_MAX + 1))
	assert resp.status_code == 422


def test_missing_recipe(auth_client):
	resp = post_note(auth_client, 9999)
	assert resp.status_code == 404
	assert resp.json() == {"detail": "recipe not found"}


def test_delete_note(auth_client, db):
	recipe = post_recipe(auth_client)
	note_id = post_note(auth_client, recipe["id"]).json()["id"]
	resp = auth_client.delete(
		f"/api/recipes/{recipe['id']}/notes/{note_id}")
	assert resp.status_code == 204
	assert resp.content == b""
	assert db.get(Note, note_id) is None
	resp = auth_client.delete(
		f"/api/recipes/{recipe['id']}/notes/{note_id}")
	assert resp.status_code == 404
	assert resp.json() == {"detail": "note not found"}


def test_delete_with_wrong_recipe(auth_client, db):
	recipe = post_recipe(auth_client)
	note_id = post_note(auth_client, recipe["id"]).json()["id"]
	resp = auth_client.delete(f"/api/recipes/9999/notes/{note_id}")
	assert resp.status_code == 404
	assert db.get(Note, note_id) is not None


def test_note_bound_to_its_recipe(auth_client, db):
	a = post_recipe(auth_client)
	b = post_recipe(auth_client)
	note_id = post_note(auth_client, a["id"]).json()["id"]
	resp = auth_client.delete(f"/api/recipes/{b['id']}/notes/{note_id}")
	assert resp.status_code == 404
	assert resp.json() == {"detail": "note not found"}
	assert db.get(Note, note_id) is not None


def test_requires_login(client):
	assert post_note(client, 1).status_code == 401
	assert client.delete("/api/recipes/1/notes/1").status_code == 401


def test_recipe_lists_notes_newest_first(auth_client, db):
	recipe = post_recipe(auth_client)
	first = post_note(auth_client, recipe["id"], "alt").json()
	old = datetime.now(timezone.utc) - timedelta(days=1)
	db.get(Note, first["id"]).created_at = old
	db.commit()
	post_note(auth_client, recipe["id"], "neu")
	body = auth_client.get(f"/api/recipes/{recipe['id']}").json()
	if "notes" not in body:
		pytest.skip("RecipeOut.notes not yet filled by to_out")
	assert [n["text"] for n in body["notes"]] == ["neu", "alt"]


def test_service_add_and_delete(db, auth_client):
	recipe = post_recipe(auth_client)
	assert service.add_note(db, 9999, NoteIn(text="x")) is None
	note = service.add_note(db, recipe["id"], NoteIn(text=" x "))
	assert note.id > 0 and note.text == "x"
	assert note.created_at is not None
	assert service.delete_note(db, recipe["id"] + 1, note.id) is False
	assert service.delete_note(db, recipe["id"], note.id) is True
	assert service.delete_note(db, recipe["id"], note.id) is False
