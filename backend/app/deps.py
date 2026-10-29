"""FastAPI dependencies shared by routers."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME
from app.db import get_db
from app.models import User
from app.services import auth as auth_service

NOT_LOGGED_IN = "not logged in"


def current_user(request: Request,
		 db: Session = Depends(get_db)) -> User:
	token = request.cookies.get(COOKIE_NAME)
	user = None
	if token:
		user = auth_service.user_for_token(db, token)
	if user is None:
		raise HTTPException(status_code=401, detail=NOT_LOGGED_IN)
	return user
