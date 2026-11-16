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

# A real hash to verify against when the username is unknown, so a
# login attempt costs the same time whether or not the user exists and
# cannot be used to probe which usernames are taken.
_DUMMY_HASH = _hasher.hash("no such user")


def hash_password(pw: str) -> str:
	return _hasher.hash(pw)


def verify_password(hash_: str, pw: str) -> bool:
	try:
		return _hasher.verify(hash_, pw)
	except (VerificationError, InvalidHashError):
		return False


def spend_verify_time(pw: str) -> None:
	"""Match the timing of a real verify when the user is missing."""
	verify_password(_DUMMY_HASH, pw)


def new_token() -> str:
	return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
	return hashlib.sha256(token.encode("utf-8")).hexdigest()


def now_utc() -> datetime:
	return datetime.now(timezone.utc)


def session_expiry() -> datetime:
	return now_utc() + timedelta(days=settings.session_days)
