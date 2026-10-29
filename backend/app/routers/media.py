"""Serve stored photos. Mounted at the app root, not under /api."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import storage
from app.db import get_db
from app.deps import current_user
from app.services import share

NOT_FOUND = "media not found"
MEDIA_TYPE = "image/jpeg"
CACHE_CONTROL = "private, max-age=86400"

router = APIRouter()


def file_response(name: str) -> FileResponse:
	try:
		if not storage.exists(name):
			raise ValueError(name)
		path = storage.media_path(name)
	except ValueError:
		raise HTTPException(status_code=404, detail=NOT_FOUND)
	return FileResponse(path, media_type=MEDIA_TYPE,
			    headers={"Cache-Control": CACHE_CONTROL})


@router.get("/media/{name}", dependencies=[Depends(current_user)])
def get_media(name: str):
	return file_response(name)


@router.get("/share/{token}/photos/{photo_id}.jpg")
def get_shared_photo(token: str, photo_id: int,
		     db: Session = Depends(get_db)):
	"""Full-size photo of a shared recipe, no login; else 404."""
	photo = share.shared_photo(db, token, photo_id)
	if photo is None:
		raise HTTPException(status_code=404, detail=NOT_FOUND)
	return file_response(storage.photo_name(photo.id))
