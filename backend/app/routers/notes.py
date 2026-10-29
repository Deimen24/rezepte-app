"""Note endpoints under /recipes/{id}/notes."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.schemas import NoteIn, NoteOut
from app.services import notes as service

RECIPE_NOT_FOUND = "recipe not found"
NOTE_NOT_FOUND = "note not found"

router = APIRouter(prefix="/recipes", dependencies=[Depends(current_user)])


@router.post("/{recipe_id}/notes", response_model=NoteOut, status_code=201)
def add_note(recipe_id: int, data: NoteIn, db: Session = Depends(get_db)):
	note = service.add_note(db, recipe_id, data)
	if note is None:
		raise HTTPException(status_code=404, detail=RECIPE_NOT_FOUND)
	return NoteOut.model_validate(note)


@router.delete("/{recipe_id}/notes/{note_id}", status_code=204)
def delete_note(recipe_id: int, note_id: int,
		db: Session = Depends(get_db)):
	if not service.delete_note(db, recipe_id, note_id):
		raise HTTPException(status_code=404, detail=NOTE_NOT_FOUND)
	return Response(status_code=204)
