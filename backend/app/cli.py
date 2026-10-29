"""Admin commands: python -m app.cli <command> [args]."""

import argparse
import getpass
import os
import sys

from app.db import SessionLocal
from app.services import auth as auth_service

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


def cmd_create_user(args) -> None:
	pw = read_password()
	with SessionLocal() as db:
		try:
			auth_service.create_user(db, args.username, pw)
		except ValueError:
			sys.exit("Fehler: Benutzer '%s' existiert bereits."
				 % args.username)
	print("Benutzer '%s' angelegt." % args.username)


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


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(prog="python -m app.cli",
				    description="Verwaltung der Rezepte-App")
	sub = p.add_subparsers(dest="command", required=True)

	c = sub.add_parser("create-user", help="Benutzer anlegen")
	c.add_argument("username")
	c.set_defaults(func=cmd_create_user)

	s = sub.add_parser("set-password", help="Passwort setzen")
	s.add_argument("username")
	s.set_defaults(func=cmd_set_password)

	g = sub.add_parser("purge-sessions",
			   help="abgelaufene Sitzungen loeschen")
	g.set_defaults(func=cmd_purge_sessions)
	return p


def main(argv=None) -> None:
	args = build_parser().parse_args(argv)
	args.func(args)


if __name__ == "__main__":
	main()
