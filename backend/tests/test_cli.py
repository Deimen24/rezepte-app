"""Admin CLI run in-process against a SQLite file database."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app import auth, cli
from app.models import Base, Session, User
from app.services import auth as auth_service

USER = "anna"
PASSWORD = "geheim"


def _sqlite_fk(conn, record):
	cur = conn.cursor()
	cur.execute("PRAGMA foreign_keys=ON")
	cur.close()


@pytest.fixture
def cli_db(tmp_path, monkeypatch):
	"""Point the CLI at a fresh file database; yield a session on it."""
	engine = create_engine("sqlite:///" + str(tmp_path / "cli.db"))
	event.listen(engine, "connect", _sqlite_fk)
	Base.metadata.create_all(engine)
	factory = sessionmaker(bind=engine, autoflush=False,
			       expire_on_commit=False)
	# cli.py imported SessionLocal by name; swap that binding.
	monkeypatch.setattr(cli, "SessionLocal", factory)
	monkeypatch.setenv(cli.PASSWORD_ENV, PASSWORD)
	db = factory()
	try:
		yield db
	finally:
		db.close()
		engine.dispose()


def run(argv) -> None:
	cli.main(argv)


def test_create_user_then_login_works(cli_db, capsys):
	run(["create-user", USER])
	assert "'%s' angelegt" % USER in capsys.readouterr().out
	assert cli_db.scalars(select(User.username)).all() == [USER]
	assert auth_service.login(cli_db, USER, PASSWORD) is not None
	assert auth_service.login(cli_db, USER, "falsch") is None


def test_create_user_stores_hash_not_password(cli_db):
	run(["create-user", USER])
	user = cli_db.scalar(select(User))
	assert PASSWORD not in user.password_hash
	assert auth.verify_password(user.password_hash, PASSWORD)


def test_duplicate_create_user_exits_nonzero(cli_db, capsys):
	run(["create-user", USER])
	with pytest.raises(SystemExit) as exc:
		run(["create-user", USER])
	# sys.exit(message) prints the message and exits with status 1.
	assert exc.value.code not in (0, None)
	assert USER in str(exc.value.code)
	assert "existiert bereits" in str(exc.value.code)
	assert cli_db.scalar(select(User.username).where(
		User.username == USER)) == USER
	assert len(cli_db.scalars(select(User)).all()) == 1


def test_set_password_changes_password(cli_db, monkeypatch):
	run(["create-user", USER])
	monkeypatch.setenv(cli.PASSWORD_ENV, "neu")
	run(["set-password", USER])
	assert auth_service.login(cli_db, USER, PASSWORD) is None
	assert auth_service.login(cli_db, USER, "neu") is not None


def test_set_password_unknown_user_exits_nonzero(cli_db):
	with pytest.raises(SystemExit) as exc:
		run(["set-password", "niemand"])
	assert exc.value.code not in (0, None)
	assert "nicht gefunden" in str(exc.value.code)


def test_purge_sessions_removes_only_expired(cli_db, capsys):
	run(["create-user", USER])
	old = auth_service.login(cli_db, USER, PASSWORD)
	fresh = auth_service.login(cli_db, USER, PASSWORD)
	sess = cli_db.scalar(select(Session).where(
		Session.token_hash == auth.hash_token(old)))
	sess.expires_at = auth.now_utc() - timedelta(days=1)
	cli_db.commit()

	run(["purge-sessions"])

	assert "1 abgelaufene" in capsys.readouterr().out
	cli_db.expire_all()
	hashes = cli_db.scalars(select(Session.token_hash)).all()
	assert hashes == [auth.hash_token(fresh)]


def test_purge_sessions_on_empty_table_reports_zero(cli_db, capsys):
	run(["purge-sessions"])
	assert capsys.readouterr().out.startswith("0 ")


def test_password_from_env_skips_prompt(cli_db, monkeypatch):
	def no_prompt(*args, **kwargs):
		raise AssertionError("getpass must not be called")

	monkeypatch.setattr(cli.getpass, "getpass", no_prompt)
	run(["create-user", USER])
	assert auth_service.login(cli_db, USER, PASSWORD) is not None


def test_password_prompt_mismatch_exits(cli_db, monkeypatch):
	monkeypatch.delenv(cli.PASSWORD_ENV)
	answers = iter(["eins", "zwei"])
	monkeypatch.setattr(cli.getpass, "getpass",
			    lambda prompt: next(answers))
	with pytest.raises(SystemExit) as exc:
		run(["create-user", USER])
	assert "stimmen nicht" in str(exc.value.code)
	assert cli_db.scalars(select(User)).all() == []


def test_missing_command_exits_with_usage_error(cli_db):
	with pytest.raises(SystemExit) as exc:
		run([])
	assert exc.value.code == 2
