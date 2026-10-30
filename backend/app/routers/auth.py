"""Login, logout and whoami. Mounted under /api by main.py."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME
from app.config import settings
from app.db import get_db
from app.deps import current_user
from app.models import User
from app.services import auth as auth_service

SECONDS_PER_DAY = 86400
WRONG_CREDENTIALS = "wrong credentials"
SETUP_DONE = "setup already done"
MIN_PASSWORD_LEN = 8
MAX_NAME_LEN = 200

router = APIRouter(prefix="/auth")


class LoginInput(BaseModel):
	username: str
	password: str


class SetupInput(BaseModel):
	username: str = Field(min_length=1, max_length=MAX_NAME_LEN)
	password: str = Field(min_length=MIN_PASSWORD_LEN)

	@field_validator("username", mode="before")
	@classmethod
	def strip_name(cls, value):
		return value.strip() if isinstance(value, str) else value


def _set_cookie(resp: Response, token: str) -> None:
	resp.set_cookie(COOKIE_NAME, token, httponly=True,
			secure=settings.cookie_secure, samesite="lax",
			max_age=settings.session_days * SECONDS_PER_DAY,
			path="/")


def _clear_cookie(resp: Response) -> None:
	resp.delete_cookie(COOKIE_NAME, path="/", httponly=True,
			   secure=settings.cookie_secure, samesite="lax")


@router.get("/setup")
def setup_state(db: Session = Depends(get_db)):
	"""Public: tells the login screen whether the first user is
	missing."""
	return {"needed": not auth_service.has_users(db)}


@router.post("/setup", status_code=201)
def setup(body: SetupInput, resp: Response,
	  db: Session = Depends(get_db)):
	"""Create the single user on first use and log in."""
	if auth_service.has_users(db):
		raise HTTPException(status_code=409, detail=SETUP_DONE)
	auth_service.create_user(db, body.username, body.password)
	token = auth_service.login(db, body.username, body.password)
	_set_cookie(resp, token)
	return {"username": body.username}


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
