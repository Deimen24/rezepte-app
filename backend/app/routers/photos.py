"""Photo upload and removal per recipe."""

from fastapi import (
	APIRouter,
	Depends,
	Form,
	HTTPException,
	Response,
	UploadFile,
)
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.importer.fetch import FetchError
from app.schemas import PhotoOut, PhotoUrlIn
from app.services import photos as service
from app.services.photos import MAX_UPLOAD

RECIPE_NOT_FOUND = "recipe not found"
PHOTO_NOT_FOUND = "photo not found"
TOO_LARGE = "file too large"
NOT_IMAGE = "not an image"

router = APIRouter(prefix="/recipes", dependencies=[Depends(current_user)])


async def read_upload(file: UploadFile) -> bytes:
	"""Read at most MAX_UPLOAD bytes; one byte more means 413."""
	data = await file.read(MAX_UPLOAD + 1)
	if len(data) > MAX_UPLOAD:
		raise HTTPException(status_code=413, detail=TOO_LARGE)
	return data


@router.post("/{recipe_id}/photos", response_model=PhotoOut,
	     status_code=201)
async def upload_photo(recipe_id: int, file: UploadFile,
		       is_own_result: bool = Form(False),
		       db: Session = Depends(get_db)):
	data = await read_upload(file)
	try:
		photo = service.add_photo(db, recipe_id, data, is_own_result)
	except ValueError:
		raise HTTPException(status_code=415, detail=NOT_IMAGE)
	if photo is None:
		raise HTTPException(status_code=404, detail=RECIPE_NOT_FOUND)
	return service.to_out(photo)


@router.post("/{recipe_id}/photos/url", response_model=PhotoOut,
	     status_code=201)
def photo_from_url(recipe_id: int, body: PhotoUrlIn,
		   db: Session = Depends(get_db)):
	try:
		photo = service.add_photo_from_url(db, recipe_id, body.url)
	except FetchError as e:
		raise HTTPException(status_code=422, detail=e.detail)
	except ValueError:
		raise HTTPException(status_code=415, detail=NOT_IMAGE)
	if photo is None:
		raise HTTPException(status_code=404, detail=RECIPE_NOT_FOUND)
	return service.to_out(photo)


@router.delete("/{recipe_id}/photos/{photo_id}", status_code=204)
def delete_photo(recipe_id: int, photo_id: int,
		 db: Session = Depends(get_db)):
	if not service.delete_photo(db, recipe_id, photo_id):
		raise HTTPException(status_code=404, detail=PHOTO_NOT_FOUND)
	return Response(status_code=204)
