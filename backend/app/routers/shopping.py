"""Shopping list endpoints under /shopping."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.schemas import (
	CheckedIn,
	ShoppingFromRecipeIn,
	ShoppingItemIn,
	ShoppingItemOut,
)
from app.services import shopping as service

RECIPE_NOT_FOUND = "recipe not found"
ITEM_NOT_FOUND = "item not found"

router = APIRouter(prefix="/shopping",
		   dependencies=[Depends(current_user)])


def to_out(item) -> ShoppingItemOut:
	return ShoppingItemOut.model_validate(item)


def item_or_404(item) -> ShoppingItemOut:
	if item is None:
		raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)
	return to_out(item)


@router.get("", response_model=list[ShoppingItemOut])
def list_items(db: Session = Depends(get_db)):
	return [to_out(i) for i in service.list_items(db)]


@router.post("", response_model=ShoppingItemOut, status_code=201)
def add_item(data: ShoppingItemIn, db: Session = Depends(get_db)):
	return to_out(service.add_item(db, data))


@router.post("/from-recipe/{recipe_id}",
	     response_model=list[ShoppingItemOut])
def add_from_recipe(recipe_id: int, data: ShoppingFromRecipeIn,
		    db: Session = Depends(get_db)):
	items = service.add_from_recipe(db, recipe_id, data.factor)
	if items is None:
		raise HTTPException(status_code=404, detail=RECIPE_NOT_FOUND)
	return [to_out(i) for i in items]


# before /{item_id}, otherwise "checked" would be parsed as an id
@router.delete("/checked", status_code=204)
def clear_checked(db: Session = Depends(get_db)):
	service.clear_checked(db)
	return Response(status_code=204)


@router.put("/{item_id}", response_model=ShoppingItemOut)
def update_item(item_id: int, data: ShoppingItemIn,
		db: Session = Depends(get_db)):
	return item_or_404(service.update_item(db, item_id, data))


@router.put("/{item_id}/checked", response_model=ShoppingItemOut)
def set_checked(item_id: int, data: CheckedIn,
		db: Session = Depends(get_db)):
	return item_or_404(service.set_checked(db, item_id, data.checked))


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
	if not service.delete_item(db, item_id):
		raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)
	return Response(status_code=204)
