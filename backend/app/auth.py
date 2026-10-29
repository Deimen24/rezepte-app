"""Password hashing and session token helpers. No HTTP here."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

COOKIE_NAME = "session"
TOKEN_BYTES = 32

_hasher = PasswordHasher()


def hash_password(pw: str) -> str:
	return _hasher.hash(pw)


def verify_password(hash_: str, pw: str) -> bool:
	try:
		return _hasher.verify(hash_, pw)
	except (VerificationError, InvalidHashError):
		return False


def new_token() -> str:
	return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
	return hashlib.sha256(token.encode("utf-8")).hexdigest()


def now_utc() -> datetime:
	return datetime.now(timezone.utc)


def session_expiry() -> datetime:
	return now_utc() + timedelta(days=settings.session_days)
