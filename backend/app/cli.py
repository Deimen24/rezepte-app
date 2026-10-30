"""Admin commands: python -m app.cli <command> [args]."""

import argparse
import getpass
import os
import sys

from app.db import SessionLocal
from app.services import auth as auth_service
from app.services import todo as todo_service

PASSWORD_ENV = "REZEPTE_PASSWORD"
MIN_PASSWORD_LEN = 1


def read_password() -> str:
	pw = os.environ.get(PASSWORD_ENV)
	if pw:
		return pw
	pw = getpass.getpass("Passwort: ")
	again = getpass.getpass("Passwort wiederholen: ")
	if pw != again:
		sys.exit("Fehler: Die Passwoerter stimmen nicht ueberein.")
	if len(pw) < MIN_PASSWORD_LEN:
		sys.exit("Fehler: Das Passwort darf nicht leer sein.")
	return pw


def cmd_set_password(args) -> None:
	pw = read_password()
	with SessionLocal() as db:
		try:
			auth_service.set_password(db, args.username, pw)
		except ValueError:
			sys.exit("Fehler: Benutzer '%s' nicht gefunden."
				 % args.username)
	print("Passwort fuer '%s' gesetzt." % args.username)


def cmd_purge_sessions(args) -> None:
	with SessionLocal() as db:
		n = auth_service.purge_expired(db)
	print("%d abgelaufene Sitzungen geloescht." % n)


def cmd_todo_login(args) -> None:
	try:
		info = todo_service.start_device_login()
		print("Im Browser %s oeffnen und den Code %s eingeben."
		      % (info["verification_uri"], info["user_code"]))
		sys.stdout.flush()
		with SessionLocal() as db:
			todo_service.finish_device_login(
				db, info["device_code"], info["interval"])
	except todo_service.TodoError as e:
		sys.exit("Fehler: %s" % e.detail)
	print("Angemeldet.")


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(prog="python -m app.cli",
				    description="Verwaltung der Rezepte-App")
	sub = p.add_subparsers(dest="command", required=True)

	s = sub.add_parser("set-password", help="Passwort setzen")
	s.add_argument("username")
	s.set_defaults(func=cmd_set_password)

	g = sub.add_parser("purge-sessions",
			   help="abgelaufene Sitzungen loeschen")
	g.set_defaults(func=cmd_purge_sessions)

	t = sub.add_parser("todo-login",
			   help="bei Microsoft To Do anmelden")
	t.set_defaults(func=cmd_todo_login)
	return p


def main(argv=None) -> None:
	args = build_parser().parse_args(argv)
	args.func(args)


if __name__ == "__main__":
	main()
