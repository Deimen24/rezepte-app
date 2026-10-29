"""Favorite flag endpoint under /recipes/{id}/favorite."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.schemas import FavoriteIn, FavoriteOut
from app.services import favorite as service

RECIPE_NOT_FOUND = "recipe not found"

router = APIRouter(prefix="/recipes", dependencies=[Depends(current_user)])


@router.put("/{recipe_id}/favorite", response_model=FavoriteOut)
def set_favorite(recipe_id: int, data: FavoriteIn,
		 db: Session = Depends(get_db)):
	recipe = service.set_favorite(db, recipe_id, data.favorite)
	if recipe is None:
		raise HTTPException(status_code=404, detail=RECIPE_NOT_FOUND)
	return FavoriteOut(favorite=recipe.favorite)
