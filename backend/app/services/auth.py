"""User and session logic. Routers stay thin and call these."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app import auth
from app.models import Session, User


def get_user(db: DbSession, username: str) -> User | None:
	return db.scalar(select(User).where(User.username == username))


def create_user(db: DbSession, username: str, password: str) -> User:
	"""Raise ValueError if the username is already taken."""
	if get_user(db, username) is not None:
		raise ValueError("user exists: " + username)
	user = User(username=username,
		    password_hash=auth.hash_password(password))
	db.add(user)
	db.commit()
	db.refresh(user)
	return user


def set_password(db: DbSession, username: str, password: str) -> None:
	"""Raise ValueError if the user does not exist."""
	user = get_user(db, username)
	if user is None:
		raise ValueError("no such user: " + username)
	user.password_hash = auth.hash_password(password)
	db.commit()


def login(db: DbSession, username: str, password: str) -> str | None:
	"""Return a raw session token, or None on wrong credentials."""
	user = get_user(db, username)
	if user is None:
		return None
	if not auth.verify_password(user.password_hash, password):
		return None
	token = auth.new_token()
	db.add(Session(user_id=user.id, token_hash=auth.hash_token(token),
		       expires_at=auth.session_expiry()))
	db.commit()
	return token


def _find_session(db: DbSession, token: str) -> Session | None:
	return db.scalar(select(Session)
			 .where(Session.token_hash == auth.hash_token(token)))


def logout(db: DbSession, token: str) -> None:
	sess = _find_session(db, token)
	if sess is not None:
		db.delete(sess)
		db.commit()


def _as_utc(dt):
	# SQLite returns naive datetimes; treat them as UTC.
	if dt.tzinfo is None:
		return dt.replace(tzinfo=auth.now_utc().tzinfo)
	return dt


def user_for_token(db: DbSession, token: str) -> User | None:
	"""Return the user of a valid, unexpired session, else None."""
	sess = _find_session(db, token)
	if sess is None:
		return None
	if _as_utc(sess.expires_at) <= auth.now_utc():
		return None
	return db.get(User, sess.user_id)


def purge_expired(db: DbSession) -> int:
	"""Delete expired sessions, return how many were removed."""
	res = db.execute(delete(Session)
			 .where(Session.expires_at <= auth.now_utc()))
	db.commit()
	return res.rowcount
