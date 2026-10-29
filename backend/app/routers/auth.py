"""Login, logout and whoami. Mounted under /api by main.py."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME
from app.config import settings
from app.db import get_db
from app.deps import current_user
from app.models import User
from app.services import auth as auth_service

SECONDS_PER_DAY = 86400
WRONG_CREDENTIALS = "wrong credentials"

router = APIRouter(prefix="/auth")


class LoginInput(BaseModel):
	username: str
	password: str


def _set_cookie(resp: Response, token: str) -> None:
	resp.set_cookie(COOKIE_NAME, token, httponly=True,
			secure=settings.cookie_secure, samesite="lax",
			max_age=settings.session_days * SECONDS_PER_DAY,
			path="/")


def _clear_cookie(resp: Response) -> None:
	resp.delete_cookie(COOKIE_NAME, path="/", httponly=True,
			   secure=settings.cookie_secure, samesite="lax")


@router.post("/login")
def login(body: LoginInput, resp: Response,
	  db: Session = Depends(get_db)):
	token = auth_service.login(db, body.username, body.password)
	if token is None:
		raise HTTPException(status_code=401, detail=WRONG_CREDENTIALS)
	_set_cookie(resp, token)
	return {"username": body.username}


@router.post("/logout")
def logout(request: Request, resp: Response,
	   db: Session = Depends(get_db)):
	token = request.cookies.get(COOKIE_NAME)
	if token:
		auth_service.logout(db, token)
	_clear_cookie(resp)
	return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
	return {"username": user.username}
