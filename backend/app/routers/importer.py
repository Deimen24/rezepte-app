"""Recipe import from a URL and ingredient line parsing."""

from fastapi import APIRouter, Depends, HTTPException

from app.deps import current_user
from app.importer.fetch import FetchError
from app.schemas import (
	ImportIn,
	ImportPreview,
	IngredientLinesIn,
	ParsedIngredient,
)
from app.services import importer as service

router = APIRouter(prefix="/import", dependencies=[Depends(current_user)])


@router.post("/fetch", response_model=ImportPreview)
def fetch_preview(body: ImportIn):
	try:
		return service.preview(body.url)
	except FetchError as e:
		raise HTTPException(status_code=422, detail=e.detail)


@router.post("/ingredients", response_model=list[ParsedIngredient])
def parse_ingredients(body: IngredientLinesIn):
	return service.parse_ingredient_lines(body.lines)
