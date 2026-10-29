"""Export endpoint: the whole collection as a ZIP download."""

from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.services import export as service

FILENAME_FMT = "rezepte-%Y%m%d-%H%M.zip"

router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/export")
def export_zip(db: Session = Depends(get_db)):
	data, _stats = service.build_zip(db)
	name = datetime.now().strftime(FILENAME_FMT)
	return Response(
		content=data,
		media_type="application/zip",
		headers={"Content-Disposition":
			 'attachment; filename="%s"' % name},
	)
