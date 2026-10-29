"""Database engine and session factory."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings

SQLITE_PREFIX = "sqlite"


def _engine_args(url: str) -> dict:
	if url.startswith(SQLITE_PREFIX):
		return {"connect_args": {"check_same_thread": False}}
	return {}


engine = create_engine(settings.database_url,
		       **_engine_args(settings.database_url))

if settings.database_url.startswith(SQLITE_PREFIX):
	@event.listens_for(engine, "connect")
	def _sqlite_fk(conn, record):
		# SQLite ignores ON DELETE unless foreign keys are enabled.
		cur = conn.cursor()
		cur.execute("PRAGMA foreign_keys=ON")
		cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False,
			    expire_on_commit=False)


def get_db():
	"""FastAPI dependency: one database session per request."""
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()
