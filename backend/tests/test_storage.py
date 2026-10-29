"""Media storage: paths stay below media_dir, files round-trip."""

from pathlib import Path

import pytest

from app import storage
from app.config import settings


@pytest.fixture
def media_dir(tmp_path, monkeypatch) -> Path:
	root = tmp_path / "media"
	monkeypatch.setattr(settings, "media_dir", str(root))
	return root


def test_save_exists_read_delete_round_trip(media_dir):
	assert not storage.exists("a.jpg")
	path = storage.save("a.jpg", b"\xff\xd8data")
	assert path == media_dir / "a.jpg"
	assert storage.exists("a.jpg")
	with storage.open_read("a.jpg") as fh:
		assert fh.read() == b"\xff\xd8data"
	storage.delete("a.jpg")
	assert not storage.exists("a.jpg")
	assert not path.exists()


def test_save_creates_media_dir_on_demand(media_dir):
	assert not media_dir.exists()
	storage.save("b.png", b"x")
	assert media_dir.is_dir()


def test_save_overwrites_existing_file(media_dir):
	storage.save("c.jpg", b"old")
	storage.save("c.jpg", b"new")
	with storage.open_read("c.jpg") as fh:
		assert fh.read() == b"new"


def test_delete_missing_file_is_noop(media_dir):
	storage.ensure_dir()
	storage.delete("nope.jpg")
	assert not storage.exists("nope.jpg")


def test_open_read_missing_file_raises(media_dir):
	storage.ensure_dir()
	with pytest.raises(FileNotFoundError):
		storage.open_read("nope.jpg")


@pytest.mark.parametrize("name", ["../x", "../../etc/passwd",
				  "/etc/passwd", "a/b", "", ".", "..",
				  "sub/../x"])
def test_media_path_rejects_traversal_and_nested_names(media_dir, name):
	with pytest.raises(ValueError):
		storage.media_path(name)


def test_media_path_accepts_plain_file_names(media_dir):
	assert storage.media_path("photo-1.jpg") == media_dir / "photo-1.jpg"
	assert storage.media_path(".hidden") == media_dir / ".hidden"


def test_media_path_rejection_writes_nothing(media_dir):
	with pytest.raises(ValueError):
		storage.save("../escape.txt", b"x")
	assert not (media_dir.parent / "escape.txt").exists()


def test_ensure_dir_is_idempotent(media_dir):
	first = storage.ensure_dir()
	(media_dir / "keep.jpg").write_bytes(b"k")
	second = storage.ensure_dir()
	assert first == second == media_dir.resolve()
	assert (media_dir / "keep.jpg").read_bytes() == b"k"


def test_root_follows_settings(media_dir, tmp_path, monkeypatch):
	other = tmp_path / "other"
	monkeypatch.setattr(settings, "media_dir", str(other))
	assert storage.ensure_dir() == other.resolve()
	assert storage.media_path("x.jpg").parent == other.resolve()
