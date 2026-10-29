"""Export: one ZIP with recipes.json and every stored photo file."""

import io
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.models import Photo, Recipe
from app.routers.recipes import to_out
from app.schemas import CategoryOut, TagOut
from app.services import taxonomy
from app.services.recipes import LOAD_ALL

EXPORT_VERSION = 1
JSON_NAME = "recipes.json"
PHOTO_DIR = "photos/"


def all_recipes(db: Session) -> list[Recipe]:
	stmt = select(Recipe).options(*LOAD_ALL).order_by(Recipe.id)
	return list(db.scalars(stmt))


def export_json(db: Session, recipes: list[Recipe]) -> dict:
	return {
		"exported_at": datetime.now(timezone.utc).isoformat(),
		"version": EXPORT_VERSION,
		"categories": [CategoryOut.model_validate(c).model_dump()
			       for c in taxonomy.list_categories(db)],
		"tags": [TagOut.model_validate(t).model_dump()
			 for t in taxonomy.list_tags(db)],
		"recipes": [to_out(r).model_dump(mode="json")
			    for r in recipes],
	}


def photo_files(db: Session) -> list[str]:
	"""Full-size and thumbnail name of every photo row."""
	names = []
	for pid in db.scalars(select(Photo.id).order_by(Photo.id)):
		names.append(storage.photo_name(pid))
		names.append(storage.photo_name(pid, thumb=True))
	return names


def add_photos(zf: zipfile.ZipFile, names: list[str]) -> tuple[int, int]:
	"""Store existing files; return (added, missing)."""
	added = missing = 0
	for name in names:
		if not storage.exists(name):
			missing += 1
			continue
		with storage.open_read(name) as f:
			zf.writestr(PHOTO_DIR + name, f.read(),
				    compress_type=zipfile.ZIP_STORED)
		added += 1
	return added, missing


def build_zip(db: Session) -> tuple[bytes, dict]:
	recipes = all_recipes(db)
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as zf:
		data = json.dumps(export_json(db, recipes),
				  ensure_ascii=False, indent=1)
		zf.writestr(JSON_NAME, data,
			    compress_type=zipfile.ZIP_DEFLATED)
		added, missing = add_photos(zf, photo_files(db))
	stats = {"recipes": len(recipes), "photos": added,
		 "missing": missing}
	return buf.getvalue(), stats
