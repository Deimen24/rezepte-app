"""Microsoft To Do: status and pushing the shopping list."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.schemas import TodoPushOut, TodoStatus
from app.services import todo as service
from app.services.todo import TodoError

router = APIRouter(prefix="/todo", dependencies=[Depends(current_user)])


@router.get("/status", response_model=TodoStatus)
def todo_status(db: Session = Depends(get_db)):
	return service.status(db)


@router.post("/push", response_model=TodoPushOut)
def todo_push(db: Session = Depends(get_db)):
	try:
		return service.push(db)
	except TodoError as e:
		raise HTTPException(status_code=422, detail=e.detail)
