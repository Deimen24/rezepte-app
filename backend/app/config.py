"""Application settings, read from environment variables."""

from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings

DB_URL_FMT = "postgresql+psycopg://{user}:{pw}@{host}:{port}/{name}"
DEFAULT_DB_URL = "postgresql+psycopg://rezepte:rezepte@db:5432/rezepte"
DEFAULT_MEDIA_DIR = "/data/media"
DEFAULT_SESSION_DAYS = 30


class Settings(BaseSettings):
	"""Env var names are the uppercased field names."""

	app_name: str = "Rezepte"
	database_url: str = ""
	db_host: str = "db"
	db_port: int = 5432
	db_user: str = "rezepte"
	db_name: str = "rezepte"
	db_password: str = ""
	media_dir: str = DEFAULT_MEDIA_DIR
	session_days: int = DEFAULT_SESSION_DAYS
	cookie_secure: bool = True
	api_docs: bool = False

	@model_validator(mode="after")
	def build_db_url(self):
		"""DATABASE_URL wins; otherwise assemble it from DB_* parts
		so a password with special characters is quoted correctly."""
		if self.database_url:
			return self
		if not self.db_password:
			self.database_url = DEFAULT_DB_URL
			return self
		self.database_url = DB_URL_FMT.format(
			user=quote(self.db_user, safe=""),
			pw=quote(self.db_password, safe=""),
			host=self.db_host, port=self.db_port,
			name=self.db_name)
		return self


settings = Settings()
