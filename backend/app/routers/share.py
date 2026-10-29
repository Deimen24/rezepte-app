"""Share endpoints: toggling needs login, reading by token does not."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import Recipe
from app.schemas import SharedRecipe, ShareOut
from app.services import share as service

RECIPE_NOT_FOUND = "recipe not found"
NOT_FOUND = "not found"

router = APIRouter(prefix="/recipes", dependencies=[Depends(current_user)])
public_router = APIRouter(prefix="/share")


def to_out(recipe: Recipe) -> ShareOut:
	token = recipe.share_token
	path = service.share_path(token) if token else None
	return ShareOut(token=token, path=path)


def found(recipe: Recipe | None) -> Recipe:
	if recipe is None:
		raise HTTPException(status_code=404, detail=RECIPE_NOT_FOUND)
	return recipe


@router.get("/{recipe_id}/share", response_model=ShareOut)
def get_share(recipe_id: int, db: Session = Depends(get_db)):
	return to_out(found(db.get(Recipe, recipe_id)))


@router.post("/{recipe_id}/share", response_model=ShareOut)
def enable_share(recipe_id: int, db: Session = Depends(get_db)):
	return to_out(found(service.enable(db, recipe_id)))


@router.delete("/{recipe_id}/share", response_model=ShareOut)
def disable_share(recipe_id: int, db: Session = Depends(get_db)):
	return to_out(found(service.disable(db, recipe_id)))


@public_router.get("/{token}", response_model=SharedRecipe)
def get_shared(token: str, db: Session = Depends(get_db)):
	recipe = service.get_shared(db, token)
	if recipe is None:
		raise HTTPException(status_code=404, detail=NOT_FOUND)
	return service.to_shared(recipe)
