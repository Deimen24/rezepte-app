"""Shopping list: manual items and items taken from a recipe.

Lines are merged when name and unit match after normalisation (case,
whitespace, unit aliases such as "Gramm" -> "g"). Only unchecked lines
take part in a merge; a checked line is left alone and a new line is
started. Pantry staples (services.pantry) are skipped.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importer.ingredients import ALIASES
from app.models import Ingredient, ShoppingItem
from app.schemas import ShoppingItemIn
from app.services import pantry
from app.services.recipes import get_recipe

AMOUNT_STEP = Decimal("0.001")
NOTE_SEP = "; "

Key = tuple[str, str]


def norm_unit(text: str) -> str:
	low = " ".join(text.lower().split())
	return ALIASES.get(low, low)


def key_of(name: str, unit: str) -> Key:
	return pantry.norm_name(name), norm_unit(unit)


def list_items(db: Session) -> list[ShoppingItem]:
	stmt = select(ShoppingItem).order_by(
		ShoppingItem.checked, ShoppingItem.created_at, ShoppingItem.id)
	return list(db.scalars(stmt))


def add_item(db: Session, data: ShoppingItemIn) -> ShoppingItem:
	item = ShoppingItem(name=data.name, unit=data.unit,
			    amount=data.amount, note=data.note)
	db.add(item)
	db.commit()
	db.refresh(item)
	return item


def update_item(db: Session, item_id: int,
		data: ShoppingItemIn) -> ShoppingItem | None:
	item = db.get(ShoppingItem, item_id)
	if item is None:
		return None
	item.name = data.name
	item.unit = data.unit
	item.amount = data.amount
	item.note = data.note
	db.commit()
	db.refresh(item)
	return item


def set_checked(db: Session, item_id: int,
		checked: bool) -> ShoppingItem | None:
	item = db.get(ShoppingItem, item_id)
	if item is None:
		return None
	item.checked = checked
	db.commit()
	db.refresh(item)
	return item


def delete_item(db: Session, item_id: int) -> bool:
	item = db.get(ShoppingItem, item_id)
	if item is None:
		return False
	db.delete(item)
	db.commit()
	return True


def clear_checked(db: Session) -> int:
	stmt = select(ShoppingItem).where(ShoppingItem.checked.is_(True))
	items = list(db.scalars(stmt))
	for item in items:
		db.delete(item)
	db.commit()
	return len(items)


def scale(amount: Decimal | None, factor: Decimal) -> Decimal | None:
	if amount is None:
		return None
	return (amount * factor).quantize(AMOUNT_STEP, rounding=ROUND_HALF_UP)


def merge_note(old: str, new: str) -> str:
	if not new or new == old:
		return old
	if not old:
		return new
	return old + NOTE_SEP + new


def merge(item: ShoppingItem, amount: Decimal | None, note: str) -> None:
	if item.amount is None:
		item.amount = amount
	elif amount is not None:
		item.amount += amount
	item.note = merge_note(item.note, note)


def unchecked_by_key(db: Session) -> dict[Key, ShoppingItem]:
	stmt = select(ShoppingItem).where(ShoppingItem.checked.is_(False))
	return {key_of(i.name, i.unit): i for i in db.scalars(stmt)}


def add_from_recipe(db: Session, recipe_id: int,
		    factor: Decimal) -> list[ShoppingItem] | None:
	"""Put the own version's ingredients on the list; None if missing."""
	recipe = get_recipe(db, recipe_id)
	if recipe is None:
		return None
	staples = pantry.pantry_names(db)
	known = unchecked_by_key(db)
	touched: list[ShoppingItem] = []
	for ing in recipe.own.ingredients:
		if pantry.matches(ing.name, staples):
			continue
		item = put_ingredient(db, known, ing, factor, recipe_id)
		if item not in touched:
			touched.append(item)
	db.commit()
	for item in touched:
		db.refresh(item)
	return touched


def put_ingredient(db: Session, known: dict[Key, ShoppingItem],
		   ing: Ingredient, factor: Decimal,
		   recipe_id: int) -> ShoppingItem:
	amount = scale(ing.amount, factor)
	key = key_of(ing.name, ing.unit)
	item = known.get(key)
	if item is not None:
		merge(item, amount, ing.note)
		return item
	item = ShoppingItem(name=ing.name, unit=ing.unit, amount=amount,
			    note=ing.note, recipe_id=recipe_id)
	db.add(item)
	known[key] = item
	return item
