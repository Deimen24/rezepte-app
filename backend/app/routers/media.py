"""Serve stored photos. Mounted at the app root, not under /api."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app import storage
from app.deps import current_user

NOT_FOUND = "media not found"
MEDIA_TYPE = "image/jpeg"
CACHE_CONTROL = "private, max-age=86400"

router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/media/{name}")
def get_media(name: str):
	try:
		if not storage.exists(name):
			raise ValueError(name)
		path = storage.media_path(name)
	except ValueError:
		raise HTTPException(status_code=404, detail=NOT_FOUND)
	return FileResponse(path, media_type=MEDIA_TYPE,
			    headers={"Cache-Control": CACHE_CONTROL})
