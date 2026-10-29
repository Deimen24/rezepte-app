"""Favorite flag of a recipe."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Recipe


def set_favorite(db: Session, recipe_id: int,
		 favorite: bool) -> Recipe | None:
	recipe = db.get(Recipe, recipe_id)
	if recipe is None:
		return None
	recipe.favorite = favorite
	recipe.updated_at = func.now()
	db.commit()
	db.refresh(recipe)
	return recipe
