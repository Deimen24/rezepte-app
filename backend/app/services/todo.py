"""Microsoft To Do: device code login and pushing the shopping list.

OAuth 2.0 device code flow and refresh against the Microsoft identity
platform v2 endpoints with plain httpx, no MSAL. Tokens live in
Integration(name="todo") as JSON {refresh_token, access_token,
expires_at}. Every network function takes an optional httpx.Client
so tests can inject a MockTransport.
"""

import json
import time
from contextlib import contextmanager

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Integration, ShoppingItem
from app.schemas import TodoPushOut, TodoStatus, amount_to_str

AUTHORITY = "https://login.microsoftonline.com/{tenant}"
SCOPE = "Tasks.ReadWrite offline_access"
GRAPH = "https://graph.microsoft.com/v1.0"
INTEGRATION = "todo"

DEVICE_PATH = "/oauth2/v2.0/devicecode"
TOKEN_PATH = "/oauth2/v2.0/token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
LISTS_URL = GRAPH + "/me/todo/lists"
TASKS_URL = LISTS_URL + "/{list_id}/tasks"
OPEN_FILTER = "status ne 'completed'"
TIMEOUT = 15.0
SLOW_DOWN_STEP = 5
EXPIRY_MARGIN = 60
DEVICE_KEYS = ("user_code", "verification_uri", "device_code",
	       "interval", "expires_in")

NOT_CONFIGURED = "Microsoft To Do nicht eingerichtet"
NOT_LOGGED_IN = "Nicht angemeldet"
UNREACHABLE = "Microsoft To Do nicht erreichbar"
LOGIN_EXPIRED = "Anmeldung abgelaufen, bitte neu starten"
LOGIN_FAILED = "Anmeldung fehlgeschlagen: {}"

# Tests replace these.
sleep = time.sleep
clock = time.time


class TodoError(ValueError):
	"""Carries a short German message for the API response."""

	def __init__(self, detail: str):
		super().__init__(detail)
		self.detail = detail


def new_client() -> httpx.Client:
	return httpx.Client(timeout=TIMEOUT)


@contextmanager
def _client(client: httpx.Client | None):
	if client is not None:
		yield client
		return
	with new_client() as own:
		yield own


def _client_id() -> str:
	if not settings.ms_client_id:
		raise TodoError(NOT_CONFIGURED)
	return settings.ms_client_id


def _row(db: Session) -> Integration | None:
	return db.scalar(select(Integration).where(
		Integration.name == INTEGRATION))


def load_tokens(db: Session) -> dict:
	row = _row(db)
	if row is None or not row.data:
		return {}
	try:
		return json.loads(row.data)
	except ValueError:
		return {}


def save_tokens(db: Session, tokens: dict) -> None:
	row = _row(db)
	if row is None:
		row = Integration(name=INTEGRATION)
		db.add(row)
	row.data = json.dumps(tokens)
	db.commit()


def status(db: Session) -> TodoStatus:
	return TodoStatus(configured=bool(settings.ms_client_id),
			  logged_in=bool(load_tokens(db).get("refresh_token")),
			  list_name=settings.todo_list)


def _oauth(client: httpx.Client, path: str, data: dict) -> dict:
	"""Identity platform answers JSON both on success and on OAuth
	errors; anything else counts as unreachable."""
	url = AUTHORITY.format(tenant=settings.ms_tenant) + path
	try:
		resp = client.post(url, data=data)
		body = resp.json()
	except (httpx.HTTPError, ValueError):
		raise TodoError(UNREACHABLE)
	if not isinstance(body, dict):
		raise TodoError(UNREACHABLE)
	if not resp.is_success and "error" not in body:
		raise TodoError(UNREACHABLE)
	return body


def _store(db: Session, body: dict, old_refresh: str | None = None) -> str:
	"""Keep the old refresh token when the answer carries none."""
	tokens = {
		"access_token": body["access_token"],
		"refresh_token": body.get("refresh_token") or old_refresh,
		"expires_at": clock() + int(body.get("expires_in", 0)),
	}
	save_tokens(db, tokens)
	return tokens["access_token"]


def start_device_login(client: httpx.Client | None = None) -> dict:
	cid = _client_id()
	with _client(client) as c:
		body = _oauth(c, DEVICE_PATH, {"client_id": cid,
					       "scope": SCOPE})
	if "error" in body:
		raise TodoError(LOGIN_FAILED.format(
			body.get("error_description") or body["error"]))
	return {k: body[k] for k in DEVICE_KEYS}


def finish_device_login(db: Session, device_code: str, interval: int,
			client: httpx.Client | None = None) -> None:
	"""Poll the token endpoint until the user has entered the code."""
	data = {"client_id": _client_id(), "grant_type": DEVICE_GRANT,
		"device_code": device_code}
	with _client(client) as c:
		while True:
			body = _oauth(c, TOKEN_PATH, data)
			err = body.get("error")
			if err is None:
				_store(db, body)
				return
			if err == "slow_down":
				interval += SLOW_DOWN_STEP
			elif err == "expired_token":
				raise TodoError(LOGIN_EXPIRED)
			elif err != "authorization_pending":
				raise TodoError(LOGIN_FAILED.format(
					body.get("error_description") or err))
			sleep(interval)


def _refresh(db: Session, refresh_token: str, client: httpx.Client
	     ) -> str:
	body = _oauth(client, TOKEN_PATH, {
		"client_id": _client_id(), "grant_type": "refresh_token",
		"refresh_token": refresh_token, "scope": SCOPE})
	if body.get("error") == "invalid_grant":
		save_tokens(db, {})
		raise TodoError(NOT_LOGGED_IN)
	if "error" in body:
		raise TodoError(LOGIN_FAILED.format(
			body.get("error_description") or body["error"]))
	return _store(db, body, refresh_token)


def access_token(db: Session, client: httpx.Client | None = None,
		 force: bool = False) -> str:
	_client_id()
	tokens = load_tokens(db)
	if not tokens.get("refresh_token"):
		raise TodoError(NOT_LOGGED_IN)
	fresh = tokens.get("expires_at", 0) > clock() + EXPIRY_MARGIN
	if not force and fresh and tokens.get("access_token"):
		return tokens["access_token"]
	with _client(client) as c:
		return _refresh(db, tokens["refresh_token"], c)


def _send(client: httpx.Client, method: str, url: str, token: str,
	  body: dict | None) -> httpx.Response:
	try:
		return client.request(method, url, json=body, headers={
			"Authorization": "Bearer " + token})
	except httpx.HTTPError:
		raise TodoError(UNREACHABLE)


def _graph(db: Session, client: httpx.Client, method: str, url: str,
	   body: dict | None = None) -> dict:
	"""One Graph call; a 401 refreshes the token and retries once."""
	resp = _send(client, method, url, access_token(db, client), body)
	if resp.status_code == 401:
		token = access_token(db, client, force=True)
		resp = _send(client, method, url, token, body)
	if not resp.is_success:
		raise TodoError(UNREACHABLE)
	return resp.json() if resp.content else {}


def _pages(db: Session, client: httpx.Client, url: str):
	while url:
		body = _graph(db, client, "GET", url)
		yield from body.get("value", [])
		url = body.get("@odata.nextLink")


def _find_list_id(db: Session, client: httpx.Client) -> str:
	for item in _pages(db, client, LISTS_URL):
		if item.get("displayName") == settings.todo_list:
			return item["id"]
	made = _graph(db, client, "POST", LISTS_URL,
		      {"displayName": settings.todo_list})
	return made["id"]


def find_list_id(db: Session, client: httpx.Client | None = None) -> str:
	with _client(client) as c:
		return _find_list_id(db, c)


def task_title(item: ShoppingItem) -> str:
	parts = (amount_to_str(item.amount), item.unit, item.name)
	return " ".join(p.strip() for p in parts if p and p.strip())


def _norm(title: str) -> str:
	return " ".join(title.casefold().split())


def _task_body(title: str, note: str) -> dict:
	body = {"title": title}
	if note:
		body["body"] = {"content": note, "contentType": "text"}
	return body


def _open_items(db: Session) -> list[ShoppingItem]:
	from app.services.shopping import list_items
	return [i for i in list_items(db) if not i.checked]


def push(db: Session, client: httpx.Client | None = None) -> TodoPushOut:
	"""Create a task per unchecked line unless an open task with the
	same title exists."""
	items = _open_items(db)
	added = skipped = 0
	with _client(client) as c:
		url = TASKS_URL.format(list_id=_find_list_id(db, c))
		seen = {_norm(t.get("title", "")) for t in _pages(
			db, c, url + "?$filter=" + OPEN_FILTER)}
		for item in items:
			title = task_title(item)
			if _norm(title) in seen:
				skipped += 1
				continue
			_graph(db, c, "POST", url, _task_body(title, item.note))
			seen.add(_norm(title))
			added += 1
	return TodoPushOut(added=added, skipped=skipped)
