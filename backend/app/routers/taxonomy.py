"""Categories and tags: list and create."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.schemas import CategoryIn, CategoryOut, TagIn, TagOut
from app.services import taxonomy as service

router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
	return service.list_categories(db)


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, db: Session = Depends(get_db)):
	try:
		return service.create_category(db, data.name)
	except ValueError as err:
		raise HTTPException(status_code=422, detail=str(err))


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)):
	return service.list_tags(db)


@router.post("/tags", response_model=TagOut, status_code=201)
def create_tag(data: TagIn, db: Session = Depends(get_db)):
	try:
		return service.create_tag(db, data.name)
	except ValueError as err:
		raise HTTPException(status_code=422, detail=str(err))
