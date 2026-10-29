"""Media file storage. The only module that touches media files."""

from pathlib import Path

from app.config import settings

MEDIA_URL_PREFIX = "/media/"


def _root() -> Path:
	return Path(settings.media_dir).resolve()


def media_path(name: str) -> Path:
	"""Resolve a plain file name below media_dir.

	The store is flat: a name with a directory part ("a/b"), an
	empty name or any traversal ("../x") is rejected.
	"""
	root = _root()
	if not name or Path(name).name != name:
		raise ValueError("invalid media name: " + name)
	path = (root / name).resolve()
	if path == root or root not in path.parents:
		raise ValueError("invalid media name: " + name)
	return path


def ensure_dir() -> Path:
	root = _root()
	root.mkdir(parents=True, exist_ok=True)
	return root


def save(name: str, data: bytes) -> Path:
	path = media_path(name)
	ensure_dir()
	path.write_bytes(data)
	return path


def open_read(name: str):
	"""Return a binary file object; the caller closes it."""
	return open(media_path(name), "rb")


def delete(name: str) -> None:
	path = media_path(name)
	if path.is_file():
		path.unlink()


def exists(name: str) -> bool:
	return media_path(name).is_file()


def photo_name(photo_id: int, thumb: bool = False) -> str:
	"""File name of a stored photo; thumbnails carry a _t suffix."""
	return "%d%s.jpg" % (photo_id, "_t" if thumb else "")


def media_url(name: str) -> str:
	return MEDIA_URL_PREFIX + name
