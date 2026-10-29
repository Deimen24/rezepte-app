"""Cook log of a recipe: add and delete entries."""

from sqlalchemy.orm import Session

from app.models import CookLog, Recipe
from app.schemas import CookLogIn


def add_entry(db: Session, recipe_id: int,
	      data: CookLogIn) -> CookLog | None:
	if db.get(Recipe, recipe_id) is None:
		return None
	entry = CookLog(recipe_id=recipe_id, cooked_on=data.cooked_on,
			rating=data.rating, comment=data.comment)
	db.add(entry)
	db.commit()
	db.refresh(entry)
	return entry


def delete_entry(db: Session, recipe_id: int, entry_id: int) -> bool:
	entry = db.get(CookLog, entry_id)
	if entry is None or entry.recipe_id != recipe_id:
		return False
	db.delete(entry)
	db.commit()
	return True
