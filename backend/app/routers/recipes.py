"""Recipe endpoints. Thin: parse, call the service, convert."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import Recipe
from app.schemas import (
	RecipeInput,
	RecipeListItem,
	RecipeOut,
	Source,
	VersionOut,
)
from app.services import recipes as service

NOT_FOUND = "recipe not found"

router = APIRouter(prefix="/recipes", dependencies=[Depends(current_user)])


def to_out(recipe: Recipe) -> RecipeOut:
	source = Source.model_construct(
		kind=recipe.source_kind.value, url=recipe.source_url,
		book=recipe.source_book, page=recipe.source_page)
	return RecipeOut(
		id=recipe.id,
		category=recipe.category,
		tags=[t.name for t in recipe.tags],
		favorite=recipe.favorite,
		source=source,
		original=VersionOut.model_validate(recipe.original),
		own=VersionOut.model_validate(recipe.own),
		created_at=recipe.created_at,
		updated_at=recipe.updated_at,
	)


def split_csv(text: str | None) -> list[str] | None:
	if text is None:
		return None
	return [part.strip() for part in text.split(",") if part.strip()]


def not_found() -> HTTPException:
	return HTTPException(status_code=404, detail=NOT_FOUND)


@router.get("", response_model=list[RecipeListItem])
def list_recipes(q: str | None = None,
		 category: int | None = None,
		 tags: str | None = None,
		 ingredients: str | None = None,
		 favorite: bool | None = Query(default=None),
		 db: Session = Depends(get_db)):
	rows = service.list_recipes(db, q=q, category_id=category,
				    tags=split_csv(tags),
				    ingredients=split_csv(ingredients),
				    favorite=favorite)
	return [RecipeListItem.model_validate(row) for row in rows]


@router.post("", response_model=RecipeOut, status_code=201)
def create_recipe(data: RecipeInput, db: Session = Depends(get_db)):
	try:
		recipe = service.create_recipe(db, data)
	except ValueError as err:
		raise HTTPException(status_code=422, detail=str(err))
	return to_out(recipe)


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
	recipe = service.get_recipe(db, recipe_id)
	if recipe is None:
		raise not_found()
	return to_out(recipe)


@router.put("/{recipe_id}", response_model=RecipeOut)
def update_recipe(recipe_id: int, data: RecipeInput,
		  db: Session = Depends(get_db)):
	try:
		recipe = service.update_recipe(db, recipe_id, data)
	except ValueError as err:
		raise HTTPException(status_code=422, detail=str(err))
	if recipe is None:
		raise not_found()
	return to_out(recipe)


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
	if not service.delete_recipe(db, recipe_id):
		raise not_found()
	return Response(status_code=204)
