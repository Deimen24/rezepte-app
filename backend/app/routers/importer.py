"""Recipe import from a URL or a page photo, and ingredient line
parsing."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.deps import current_user
from app.importer.fetch import FetchError
from app.importer.ocr import OcrError
from app.routers.photos import NOT_IMAGE, read_upload
from app.schemas import (
	ImportIn,
	ImportPreview,
	IngredientLinesIn,
	ParsedIngredient,
)
from app.services import importer as service
from app.services import ocr

router = APIRouter(prefix="/import", dependencies=[Depends(current_user)])


@router.post("/fetch", response_model=ImportPreview)
def fetch_preview(body: ImportIn):
	try:
		return service.preview(body.url)
	except FetchError as e:
		raise HTTPException(status_code=422, detail=e.detail)


@router.post("/photo", response_model=ImportPreview)
async def photo_preview(file: UploadFile):
	data = await read_upload(file)
	try:
		return ocr.preview_from_image(data)
	except OcrError as e:
		raise HTTPException(status_code=422, detail=e.detail)
	except ValueError:
		raise HTTPException(status_code=415, detail=NOT_IMAGE)


@router.post("/ingredients", response_model=list[ParsedIngredient])
def parse_ingredients(body: IngredientLinesIn):
	return service.parse_ingredient_lines(body.lines)
