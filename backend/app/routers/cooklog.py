"""Cook log endpoints under /recipes/{id}/cooklog."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.schemas import CookLogIn, CookLogOut
from app.services import cooklog as service

RECIPE_NOT_FOUND = "recipe not found"
ENTRY_NOT_FOUND = "entry not found"

router = APIRouter(prefix="/recipes", dependencies=[Depends(current_user)])


@router.post("/{recipe_id}/cooklog", response_model=CookLogOut,
	     status_code=201)
def add_entry(recipe_id: int, data: CookLogIn,
	      db: Session = Depends(get_db)):
	entry = service.add_entry(db, recipe_id, data)
	if entry is None:
		raise HTTPException(status_code=404, detail=RECIPE_NOT_FOUND)
	return CookLogOut.model_validate(entry)


@router.delete("/{recipe_id}/cooklog/{entry_id}", status_code=204)
def delete_entry(recipe_id: int, entry_id: int,
		 db: Session = Depends(get_db)):
	if not service.delete_entry(db, recipe_id, entry_id):
		raise HTTPException(status_code=404, detail=ENTRY_NOT_FOUND)
	return Response(status_code=204)
