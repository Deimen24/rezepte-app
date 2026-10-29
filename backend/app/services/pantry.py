"""Pantry: staples that never go on the shopping list.

Matching rule (is_pantry): the ingredient name is lower-cased and its
whitespace collapsed; it is a pantry item when it equals a pantry name
or when a pantry name is one of its words. So "Öl" covers "Öl zum
Braten" and "ÖL" but not "Olivenöl"; the latter is its own entry.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PantryItem


def norm_name(text: str) -> str:
	return " ".join(text.lower().split())


def list_items(db: Session) -> list[PantryItem]:
	stmt = select(PantryItem).order_by(func.lower(PantryItem.name),
					   PantryItem.id)
	return list(db.scalars(stmt))


def find_item(db: Session, name: str) -> PantryItem | None:
	stmt = select(PantryItem).where(
		func.lower(PantryItem.name) == name.lower())
	return db.scalars(stmt).first()


def add_item(db: Session, name: str) -> PantryItem:
	"""Return the existing row when the name is already known."""
	name = " ".join(name.split())
	if not name:
		raise ValueError("name must not be empty")
	item = find_item(db, name)
	if item is not None:
		return item
	item = PantryItem(name=name)
	db.add(item)
	db.commit()
	db.refresh(item)
	return item


def remove_item(db: Session, item_id: int) -> bool:
	item = db.get(PantryItem, item_id)
	if item is None:
		return False
	db.delete(item)
	db.commit()
	return True


def pantry_names(db: Session) -> set[str]:
	return {norm_name(p.name) for p in db.scalars(select(PantryItem))}


def matches(name: str, names: set[str]) -> bool:
	norm = norm_name(name)
	if norm in names:
		return True
	return any(word in names for word in norm.split())


def is_pantry(db: Session, name: str) -> bool:
	return matches(name, pantry_names(db))
