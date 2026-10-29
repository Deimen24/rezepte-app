"""Pantry endpoints under /pantry."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.schemas import PantryIn, PantryOut
from app.services import pantry as service

ITEM_NOT_FOUND = "item not found"

router = APIRouter(prefix="/pantry", dependencies=[Depends(current_user)])


@router.get("", response_model=list[PantryOut])
def list_items(db: Session = Depends(get_db)):
	return [PantryOut.model_validate(i) for i in service.list_items(db)]


@router.post("", response_model=PantryOut, status_code=201)
def add_item(data: PantryIn, db: Session = Depends(get_db)):
	return PantryOut.model_validate(service.add_item(db, data.name))


@router.delete("/{item_id}", status_code=204)
def remove_item(item_id: int, db: Session = Depends(get_db)):
	if not service.remove_item(db, item_id):
		raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)
	return Response(status_code=204)
