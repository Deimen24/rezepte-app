"""Photo upload, delivery and removal through the API and service."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app import storage
from app.config import settings
from app.models import Photo, Recipe
from app.services import photos as service
from app.services.photos import MAX_UPLOAD
from tests.test_recipes import post_recipe

PHOTO_KEYS = {"id", "url", "thumb_url", "is_own_result", "created_at"}


@pytest.fixture
def media_dir(tmp_path, monkeypatch) -> Path:
	root = tmp_path / "media"
	monkeypatch.setattr(settings, "media_dir", str(root))
	return root


def jpeg(size=(1200, 900)) -> bytes:
	buf = BytesIO()
	Image.new("RGB", size, (10, 120, 200)).save(buf, "JPEG")
	return buf.getvalue()


def upload(client, recipe_id, data=None, own="true", name="a.jpg",
	   mime="image/jpeg"):
	return client.post(f"/api/recipes/{recipe_id}/photos",
			   files={"file": (name, data or jpeg(), mime)},
			   data={"is_own_result": own})


def photo_rows(db) -> list[Photo]:
	return list(db.scalars(select(Photo)))


def test_upload_returns_photo_out_and_writes_files(auth_client, db,
						   media_dir):
	recipe = post_recipe(auth_client)
	resp = upload(auth_client, recipe["id"])
	assert resp.status_code == 201, resp.text
	body = resp.json()
	assert set(body) == PHOTO_KEYS
	pid = body["id"]
	assert body["url"] == f"/media/{pid}.jpg"
	assert body["thumb_url"] == f"/media/{pid}_t.jpg"
	assert body["is_own_result"] is True
	assert (media_dir / f"{pid}.jpg").is_file()
	assert (media_dir / f"{pid}_t.jpg").is_file()
	full = Image.open(media_dir / f"{pid}.jpg")
	thumb = Image.open(media_dir / f"{pid}_t.jpg")
	assert full.size == (1200, 900)
	assert thumb.size == (400, 300)
	row = db.get(Photo, pid)
	assert row.filename == f"{pid}.jpg"
	assert row.recipe_id == recipe["id"]


def test_is_own_result_defaults_to_false(auth_client, media_dir):
	recipe = post_recipe(auth_client)
	resp = auth_client.post(f"/api/recipes/{recipe['id']}/photos",
				files={"file": ("a.jpg", jpeg(),
						"image/jpeg")})
	assert resp.status_code == 201, resp.text
	assert resp.json()["is_own_result"] is False


def test_get_media_serves_file(auth_client, media_dir):
	recipe = post_recipe(auth_client)
	body = upload(auth_client, recipe["id"]).json()
	resp = auth_client.get(body["url"])
	assert resp.status_code == 200
	assert resp.headers["content-type"] == "image/jpeg"
	assert resp.headers["cache-control"] == "private, max-age=86400"
	assert resp.content == (media_dir / f"{body['id']}.jpg").read_bytes()
	thumb = auth_client.get(body["thumb_url"])
	assert thumb.status_code == 200
	assert thumb.content == (
		media_dir / f"{body['id']}_t.jpg").read_bytes()


def test_get_media_requires_login(client, media_dir):
	storage.save("1.jpg", jpeg())
	assert client.get("/media/1.jpg").status_code == 401


def test_get_media_missing_is_404(auth_client, media_dir):
	storage.ensure_dir()
	resp = auth_client.get("/media/missing.jpg")
	assert resp.status_code == 404


@pytest.mark.parametrize("path", ["/media/%2e%2e%2fx",
				  "/media/..%2fx", "/media/%2e%2e"])
def test_get_media_rejects_traversal(auth_client, media_dir, path):
	media_dir.mkdir()
	(media_dir.parent / "x").write_bytes(b"secret")
	resp = auth_client.get(path)
	assert resp.status_code == 404
	assert b"secret" not in resp.content


def test_too_large_upload_is_413_and_writes_nothing(auth_client, db,
						    media_dir):
	recipe = post_recipe(auth_client)
	data = jpeg() + b"\0" * MAX_UPLOAD
	resp = upload(auth_client, recipe["id"], data=data)
	assert resp.status_code == 413
	assert resp.json() == {"detail": "file too large"}
	assert photo_rows(db) == []
	assert not media_dir.exists() or not any(media_dir.iterdir())


def test_not_an_image_is_415_and_writes_nothing(auth_client, db,
						media_dir):
	recipe = post_recipe(auth_client)
	resp = upload(auth_client, recipe["id"], data=b"hello world",
		      name="a.txt", mime="text/plain")
	assert resp.status_code == 415
	assert resp.json() == {"detail": "not an image"}
	assert photo_rows(db) == []
	assert not media_dir.exists() or not any(media_dir.iterdir())


def test_upload_to_missing_recipe_is_404(auth_client, db, media_dir):
	resp = upload(auth_client, 9999)
	assert resp.status_code == 404
	assert resp.json() == {"detail": "recipe not found"}
	assert photo_rows(db) == []


def test_upload_requires_login(client, media_dir):
	assert upload(client, 1).status_code == 401


def test_delete_photo_removes_files_and_row(auth_client, db, media_dir):
	recipe = post_recipe(auth_client)
	body = upload(auth_client, recipe["id"]).json()
	pid = body["id"]
	resp = auth_client.delete(f"/api/recipes/{recipe['id']}/photos/{pid}")
	assert resp.status_code == 204
	assert not (media_dir / f"{pid}.jpg").exists()
	assert not (media_dir / f"{pid}_t.jpg").exists()
	assert db.get(Photo, pid) is None
	again = auth_client.delete(
		f"/api/recipes/{recipe['id']}/photos/{pid}")
	assert again.status_code == 404
	assert again.json() == {"detail": "photo not found"}


def test_delete_photo_of_other_recipe_is_404(auth_client, db, media_dir):
	first = post_recipe(auth_client)
	second = post_recipe(auth_client)
	pid = upload(auth_client, first["id"]).json()["id"]
	resp = auth_client.delete(
		f"/api/recipes/{second['id']}/photos/{pid}")
	assert resp.status_code == 404
	assert db.get(Photo, pid) is not None
	assert (media_dir / f"{pid}.jpg").is_file()


def test_delete_recipe_photos_removes_all_files(auth_client, db,
						media_dir):
	recipe = post_recipe(auth_client)
	ids = [upload(auth_client, recipe["id"]).json()["id"]
	       for _ in range(3)]
	assert len(list(media_dir.iterdir())) == 6
	row = db.get(Recipe, recipe["id"])
	service.delete_recipe_photos(db, row)
	assert list(media_dir.iterdir()) == []
	for pid in ids:
		assert db.get(Photo, pid) is not None


def test_delete_recipe_removes_photo_files(auth_client, db, media_dir):
	recipe = post_recipe(auth_client)
	pid = upload(auth_client, recipe["id"]).json()["id"]
	resp = auth_client.delete(f"/api/recipes/{recipe['id']}")
	assert resp.status_code == 204
	assert list(media_dir.iterdir()) == []
	assert db.get(Photo, pid) is None


def test_recipe_out_lists_photos(auth_client, media_dir):
	recipe = post_recipe(auth_client)
	first = upload(auth_client, recipe["id"], own="true").json()
	second = upload(auth_client, recipe["id"], own="false").json()
	resp = auth_client.get(f"/api/recipes/{recipe['id']}")
	assert resp.status_code == 200
	photos = resp.json()["photos"]
	assert [p["id"] for p in photos] == [first["id"], second["id"]]
	assert [p["is_own_result"] for p in photos] == [True, False]
	assert photos[0]["url"] == first["url"]
	assert photos[0]["thumb_url"] == first["thumb_url"]


def test_service_add_photo_missing_recipe(db, media_dir):
	assert service.add_photo(db, 42, jpeg(), False) is None
	assert not media_dir.exists()


def test_service_to_out_uses_storage_names(db, auth_client, media_dir):
	recipe = post_recipe(auth_client)
	photo = service.add_photo(db, recipe["id"], jpeg(), True)
	out = service.to_out(photo)
	assert out.url == storage.media_url(photo.filename)
	assert out.thumb_url == storage.media_url(
		storage.photo_name(photo.id, thumb=True))
	assert out.is_own_result is True
	assert out.created_at is not None
