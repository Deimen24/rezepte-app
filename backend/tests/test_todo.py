"""Microsoft To Do connector: device code login, token refresh, list
lookup, duplicate-free push, API and CLI. Network via MockTransport."""

import json
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app import cli
from app.models import Integration, ShoppingItem
from app.services import todo
from app.services.todo import (
	DEVICE_GRANT,
	GRAPH,
	LOGIN_EXPIRED,
	NOT_CONFIGURED,
	NOT_LOGGED_IN,
	SCOPE,
	UNREACHABLE,
	TodoError,
)

CLIENT_ID = "11111111-2222-3333-4444-555555555555"
TENANT = "consumers"
LIST = "Einkauf"
LIST_ID = "LIST1"
DEVICE_PATH = "/%s/oauth2/v2.0/devicecode" % TENANT
TOKEN_PATH = "/%s/oauth2/v2.0/token" % TENANT
LISTS_PATH = "/v1.0/me/todo/lists"
TASKS_PATH = LISTS_PATH + "/%s/tasks" % LIST_ID
NOW = 1_000_000.0
HOUR = 3600

DEVICE = {
	"user_code": "ABCD1234",
	"device_code": "dev-code",
	"verification_uri": "https://microsoft.com/devicelogin",
	"interval": 5,
	"expires_in": 900,
	"message": "ignored",
}
TOKENS = {
	"access_token": "acc-1",
	"refresh_token": "ref-1",
	"expires_in": HOUR,
	"token_type": "Bearer",
}


def ok(body, status=200) -> httpx.Response:
	return httpx.Response(status, json=body)


def oauth_error(code: str, status=400) -> httpx.Response:
	return ok({"error": code, "error_description": code + " desc"},
		  status)


class Fake:
	"""MockTransport handler: records requests, answers from a
	table keyed by (method, path). A list is played in order with
	the last entry repeating; a callable is given the request."""

	def __init__(self):
		self.requests: list[httpx.Request] = []
		self.routes: dict = {}

	def on(self, method: str, path: str, *answers) -> None:
		self.routes[(method, path)] = list(answers)

	def __call__(self, request: httpx.Request) -> httpx.Response:
		self.requests.append(request)
		queue = self.routes.get((request.method, request.url.path))
		if not queue:
			return ok({"error": "unexpected"}, 500)
		answer = queue.pop(0) if len(queue) > 1 else queue[0]
		if callable(answer):
			return answer(request)
		return answer

	def sent(self) -> list[tuple[str, str]]:
		return [(r.method, r.url.path) for r in self.requests]

	def client(self) -> httpx.Client:
		return httpx.Client(transport=httpx.MockTransport(self))


def form(request: httpx.Request) -> dict:
	return dict(httpx.QueryParams(request.content.decode()))


def task(title: str, status="notStarted") -> dict:
	return {"id": "t-" + title, "title": title, "status": status}


def lists_with(*names) -> dict:
	return {"value": [{"id": LIST_ID if n == LIST else "x-" + n,
			   "displayName": n} for n in names]}


@pytest.fixture
def configured(monkeypatch):
	monkeypatch.setattr(todo.settings, "ms_client_id", CLIENT_ID)
	monkeypatch.setattr(todo.settings, "ms_tenant", TENANT)
	monkeypatch.setattr(todo.settings, "todo_list", LIST)
	monkeypatch.setattr(todo, "clock", lambda: NOW)


@pytest.fixture
def unconfigured(monkeypatch):
	monkeypatch.setattr(todo.settings, "ms_client_id", "")


@pytest.fixture
def sleeps(monkeypatch) -> list:
	calls: list = []
	monkeypatch.setattr(todo, "sleep", calls.append)
	return calls


@pytest.fixture
def fake() -> Fake:
	return Fake()


def logged_in(db, expires_at=NOW + HOUR, access="acc-0") -> None:
	todo.save_tokens(db, {"access_token": access,
			      "refresh_token": "ref-0",
			      "expires_at": expires_at})


def add_item(db, name, amount=None, unit="", note="", checked=False):
	db.add(ShoppingItem(name=name, unit=unit, note=note,
			    checked=checked,
			    amount=Decimal(amount) if amount else None))
	db.commit()


def graph_ready(fake: Fake, open_tasks: list[dict]) -> None:
	"""Graph answering with the list present and the given tasks;
	the task GET honours $filter like the real API."""
	fake.on("GET", LISTS_PATH, ok(lists_with("Aufgaben", LIST)))

	def tasks(request):
		flt = request.url.params.get("$filter", "")
		if "completed" in flt:
			rows = [t for t in open_tasks
				if t["status"] != "completed"]
		else:
			rows = open_tasks
		return ok({"value": rows})

	fake.on("GET", TASKS_PATH, tasks)
	fake.on("POST", TASKS_PATH, ok({"id": "new"}, 201))


# ----- status --------------------------------------------------------------

def test_status_not_configured(db, unconfigured):
	s = todo.status(db)
	assert (s.configured, s.logged_in) == (False, False)
	assert s.list_name == todo.settings.todo_list


def test_status_configured_not_logged_in(db, configured):
	s = todo.status(db)
	assert (s.configured, s.logged_in, s.list_name) == (True, False,
							    LIST)


def test_status_logged_in(db, configured):
	logged_in(db)
	assert todo.status(db).logged_in is True
	row = db.scalar(select(Integration).where(
		Integration.name == todo.INTEGRATION))
	assert "ref-0" in row.data


def test_status_survives_broken_json(db, configured):
	db.add(Integration(name=todo.INTEGRATION, data="{not json"))
	db.commit()
	assert todo.status(db).logged_in is False


# ----- device code login ---------------------------------------------------

def test_start_device_login_sends_client_id_and_scope(configured, fake):
	fake.on("POST", DEVICE_PATH, ok(DEVICE))
	info = todo.start_device_login(fake.client())
	assert info == {k: DEVICE[k] for k in todo.DEVICE_KEYS}
	req = fake.requests[0]
	assert req.url.host == "login.microsoftonline.com"
	assert form(req) == {"client_id": CLIENT_ID, "scope": SCOPE}


def test_start_device_login_not_configured(unconfigured, fake):
	with pytest.raises(TodoError) as exc:
		todo.start_device_login(fake.client())
	assert exc.value.detail == NOT_CONFIGURED
	assert fake.requests == []


def test_start_device_login_unreachable(configured):
	def boom(request):
		raise httpx.ConnectError("down")

	c = httpx.Client(transport=httpx.MockTransport(boom))
	with pytest.raises(TodoError) as exc:
		todo.start_device_login(c)
	assert exc.value.detail == UNREACHABLE


def test_start_device_login_oauth_error(configured, fake):
	fake.on("POST", DEVICE_PATH, oauth_error("invalid_client"))
	with pytest.raises(TodoError) as exc:
		todo.start_device_login(fake.client())
	assert "invalid_client" in exc.value.detail


def test_finish_device_login_pending_then_success(db, configured, fake,
						  sleeps):
	fake.on("POST", TOKEN_PATH, oauth_error("authorization_pending"),
		ok(TOKENS))
	todo.finish_device_login(db, "dev-code", 5, fake.client())
	assert sleeps == [5]
	assert len(fake.requests) == 2
	assert form(fake.requests[0]) == {"client_id": CLIENT_ID,
					  "grant_type": DEVICE_GRANT,
					  "device_code": "dev-code"}
	assert todo.load_tokens(db) == {"access_token": "acc-1",
					"refresh_token": "ref-1",
					"expires_at": NOW + HOUR}
	assert todo.status(db).logged_in is True


def test_finish_device_login_slow_down_adds_five_seconds(
		db, configured, fake, sleeps):
	fake.on("POST", TOKEN_PATH, oauth_error("slow_down"),
		oauth_error("authorization_pending"), ok(TOKENS))
	todo.finish_device_login(db, "dev-code", 5, fake.client())
	assert sleeps == [10, 10]
	assert todo.load_tokens(db)["refresh_token"] == "ref-1"


def test_finish_device_login_expired(db, configured, fake, sleeps):
	fake.on("POST", TOKEN_PATH, oauth_error("authorization_pending"),
		oauth_error("expired_token"))
	with pytest.raises(TodoError) as exc:
		todo.finish_device_login(db, "dev-code", 5, fake.client())
	assert exc.value.detail == LOGIN_EXPIRED
	assert sleeps == [5]
	assert todo.load_tokens(db) == {}


def test_finish_device_login_denied(db, configured, fake, sleeps):
	fake.on("POST", TOKEN_PATH, oauth_error("authorization_declined"))
	with pytest.raises(TodoError) as exc:
		todo.finish_device_login(db, "dev-code", 5, fake.client())
	assert "authorization_declined" in exc.value.detail
	assert sleeps == []


# ----- access token and refresh --------------------------------------------

def test_access_token_not_logged_in(db, configured, fake):
	with pytest.raises(TodoError) as exc:
		todo.access_token(db, fake.client())
	assert exc.value.detail == NOT_LOGGED_IN
	assert fake.requests == []


def test_access_token_fresh_without_request(db, configured, fake):
	logged_in(db)
	assert todo.access_token(db, fake.client()) == "acc-0"
	assert fake.requests == []


def test_access_token_refreshes_when_expired(db, configured, fake):
	logged_in(db, expires_at=NOW - 1)
	fake.on("POST", TOKEN_PATH, ok({**TOKENS, "refresh_token": "ref-2",
					"access_token": "acc-2"}))
	assert todo.access_token(db, fake.client()) == "acc-2"
	data = form(fake.requests[0])
	assert data["grant_type"] == "refresh_token"
	assert data["refresh_token"] == "ref-0"
	assert data["client_id"] == CLIENT_ID
	assert todo.load_tokens(db) == {"access_token": "acc-2",
					"refresh_token": "ref-2",
					"expires_at": NOW + HOUR}


def test_refresh_within_margin_counts_as_expired(db, configured, fake):
	logged_in(db, expires_at=NOW + todo.EXPIRY_MARGIN - 1)
	fake.on("POST", TOKEN_PATH, ok(TOKENS))
	assert todo.access_token(db, fake.client()) == "acc-1"


def test_refresh_keeps_old_refresh_token_when_none_returned(
		db, configured, fake):
	logged_in(db, expires_at=0)
	fake.on("POST", TOKEN_PATH, ok({"access_token": "acc-3",
					"expires_in": 10}))
	todo.access_token(db, fake.client())
	assert todo.load_tokens(db)["refresh_token"] == "ref-0"


def test_refresh_invalid_grant_logs_out(db, configured, fake):
	logged_in(db, expires_at=0)
	fake.on("POST", TOKEN_PATH, oauth_error("invalid_grant"))
	with pytest.raises(TodoError) as exc:
		todo.access_token(db, fake.client())
	assert exc.value.detail == NOT_LOGGED_IN
	assert todo.status(db).logged_in is False


# ----- list lookup ---------------------------------------------------------

def test_find_list_id_matches_display_name(db, configured, fake):
	logged_in(db)
	fake.on("GET", LISTS_PATH, ok(lists_with("Aufgaben", LIST)))
	assert todo.find_list_id(db, fake.client()) == LIST_ID
	assert fake.sent() == [("GET", LISTS_PATH)]
	auth = fake.requests[0].headers["authorization"]
	assert auth == "Bearer acc-0"


def test_find_list_id_creates_missing_list(db, configured, fake):
	logged_in(db)
	fake.on("GET", LISTS_PATH, ok(lists_with("Aufgaben", "einkauf")))
	fake.on("POST", LISTS_PATH, ok({"id": "NEW", "displayName": LIST},
				       201))
	assert todo.find_list_id(db, fake.client()) == "NEW"
	assert fake.sent() == [("GET", LISTS_PATH), ("POST", LISTS_PATH)]
	assert fake.requests[1].read() == b'{"displayName":"Einkauf"}'


def test_graph_error_is_unreachable(db, configured, fake):
	logged_in(db)
	fake.on("GET", LISTS_PATH, ok({"error": "x"}, 503))
	with pytest.raises(TodoError) as exc:
		todo.find_list_id(db, fake.client())
	assert exc.value.detail == UNREACHABLE


# ----- push ----------------------------------------------------------------

def test_push_skips_open_tasks_and_recreates_completed(
		db, configured, fake):
	logged_in(db)
	add_item(db, "Kürbis", "250", "g")
	add_item(db, "Salz")
	add_item(db, "Milch", "0.500", "l", note="laktosefrei")
	add_item(db, "Eier", "6", "Stk", checked=True)
	graph_ready(fake, [task("250 G  kürbis"), task("salz"),
			   task("0.5 l Milch", "completed")])

	out = todo.push(db, fake.client())

	assert (out.added, out.skipped) == (1, 2)
	posts = [r for r in fake.requests
		 if r.method == "POST" and r.url.path == TASKS_PATH]
	assert len(posts) == 1
	body = posts[0].read()
	assert body == (b'{"title":"0.5 l Milch","body":{"content":'
			b'"laktosefrei","contentType":"text"}}')
	get = [r for r in fake.requests if r.url.path == TASKS_PATH
	       and r.method == "GET"][0]
	assert get.url.params["$filter"] == "status ne 'completed'"


def test_push_titles(db, configured, fake):
	logged_in(db)
	add_item(db, "Kürbis", "250", "g")
	add_item(db, "Salz")
	add_item(db, "Milch", "0.500", "l")
	add_item(db, "Mehl", "1000")
	graph_ready(fake, [])

	out = todo.push(db, fake.client())

	assert (out.added, out.skipped) == (4, 0)
	bodies = [json.loads(r.read()) for r in fake.requests
		  if r.method == "POST" and r.url.path == TASKS_PATH]
	assert bodies == [{"title": "250 g Kürbis"}, {"title": "Salz"},
			  {"title": "0.5 l Milch"}, {"title": "1000 Mehl"}]


def test_push_dedupes_within_the_shopping_list(db, configured, fake):
	logged_in(db)
	add_item(db, "Salz")
	add_item(db, "salz")
	graph_ready(fake, [])
	out = todo.push(db, fake.client())
	assert (out.added, out.skipped) == (1, 1)


def test_push_follows_next_link(db, configured, fake):
	logged_in(db)
	add_item(db, "Salz")
	add_item(db, "Mehl")
	add_item(db, "Zucker")
	fake.on("GET", LISTS_PATH, ok(lists_with(LIST)))
	next_url = GRAPH + "/me/todo/lists/%s/tasks?$skiptoken=2" % LIST_ID
	fake.on("GET", TASKS_PATH,
		ok({"value": [task("Salz")], "@odata.nextLink": next_url}),
		ok({"value": [task("Mehl")]}))
	fake.on("POST", TASKS_PATH, ok({"id": "new"}, 201))

	out = todo.push(db, fake.client())

	assert (out.added, out.skipped) == (1, 2)
	gets = [r for r in fake.requests
		if r.method == "GET" and r.url.path == TASKS_PATH]
	assert len(gets) == 2
	assert gets[1].url.params["$skiptoken"] == "2"


def test_push_nothing_to_do(db, configured, fake):
	logged_in(db)
	graph_ready(fake, [task("Salz")])
	out = todo.push(db, fake.client())
	assert (out.added, out.skipped) == (0, 0)
	assert fake.sent() == [("GET", LISTS_PATH), ("GET", TASKS_PATH)]


def test_push_retries_once_after_401(db, configured, fake):
	logged_in(db)
	add_item(db, "Salz")
	fake.on("GET", LISTS_PATH, ok({}, 401), ok(lists_with(LIST)))
	fake.on("POST", TOKEN_PATH, ok({**TOKENS, "access_token": "acc-9"}))
	fake.on("GET", TASKS_PATH, ok({"value": []}))
	fake.on("POST", TASKS_PATH, ok({"id": "new"}, 201))

	out = todo.push(db, fake.client())

	assert out.added == 1
	assert fake.sent() == [("GET", LISTS_PATH), ("POST", TOKEN_PATH),
			       ("GET", LISTS_PATH), ("GET", TASKS_PATH),
			       ("POST", TASKS_PATH)]
	assert fake.requests[0].headers["authorization"] == "Bearer acc-0"
	for r in fake.requests[2:]:
		assert r.headers["authorization"] == "Bearer acc-9"
	assert todo.load_tokens(db)["access_token"] == "acc-9"


def test_push_second_401_is_unreachable(db, configured, fake):
	logged_in(db)
	fake.on("GET", LISTS_PATH, ok({}, 401))
	fake.on("POST", TOKEN_PATH, ok(TOKENS))
	with pytest.raises(TodoError) as exc:
		todo.push(db, fake.client())
	assert exc.value.detail == UNREACHABLE
	assert fake.sent().count(("POST", TOKEN_PATH)) == 1


def test_push_not_logged_in(db, configured, fake):
	add_item(db, "Salz")
	with pytest.raises(TodoError) as exc:
		todo.push(db, fake.client())
	assert exc.value.detail == NOT_LOGGED_IN
	assert fake.requests == []


# ----- API -----------------------------------------------------------------

STATUS = "/api/todo/status"
PUSH = "/api/todo/push"


def test_api_requires_login(client):
	assert client.get(STATUS).status_code == 401
	assert client.post(PUSH).status_code == 401


def test_api_status(auth_client, db, configured):
	assert auth_client.get(STATUS).json() == {
		"configured": True, "logged_in": False, "list_name": LIST}
	logged_in(db)
	assert auth_client.get(STATUS).json()["logged_in"] is True


def test_api_status_unconfigured(auth_client, unconfigured):
	body = auth_client.get(STATUS).json()
	assert body["configured"] is False


def test_api_push_not_configured(auth_client, unconfigured):
	r = auth_client.post(PUSH)
	assert r.status_code == 422
	assert r.json() == {"detail": NOT_CONFIGURED}


def test_api_push_not_logged_in(auth_client, configured):
	r = auth_client.post(PUSH)
	assert r.status_code == 422
	assert r.json() == {"detail": NOT_LOGGED_IN}


def test_api_push_uses_client_factory(auth_client, db, configured, fake,
				      monkeypatch):
	monkeypatch.setattr(todo, "new_client", fake.client)
	logged_in(db)
	add_item(db, "Salz")
	add_item(db, "Mehl")
	graph_ready(fake, [task("Mehl")])
	r = auth_client.post(PUSH)
	assert r.status_code == 200, r.text
	assert r.json() == {"added": 1, "skipped": 1}


def test_api_push_unreachable(auth_client, db, configured, monkeypatch):
	def boom(request):
		raise httpx.ConnectError("down")

	monkeypatch.setattr(todo, "new_client", lambda: httpx.Client(
		transport=httpx.MockTransport(boom)))
	logged_in(db)
	r = auth_client.post(PUSH)
	assert r.status_code == 422
	assert r.json() == {"detail": UNREACHABLE}


# ----- CLI -----------------------------------------------------------------

def test_cli_todo_login_prints_code_and_finishes(monkeypatch, capsys):
	calls: list = []

	class Db:
		def __enter__(self):
			return "db"

		def __exit__(self, *exc):
			return False

	monkeypatch.setattr(cli, "SessionLocal", Db)
	monkeypatch.setattr(cli.todo_service, "start_device_login",
			    lambda client=None: DEVICE)
	monkeypatch.setattr(cli.todo_service, "finish_device_login",
			    lambda *a, **kw: calls.append(a))
	cli.main(["todo-login"])
	out = capsys.readouterr().out
	assert DEVICE["verification_uri"] in out
	assert DEVICE["user_code"] in out
	assert out.rstrip().endswith("Angemeldet.")
	assert calls == [("db", "dev-code", 5)]


def test_cli_todo_login_error_exits_nonzero(monkeypatch):
	def fail(client=None):
		raise TodoError(NOT_CONFIGURED)

	monkeypatch.setattr(cli.todo_service, "start_device_login", fail)
	with pytest.raises(SystemExit) as exc:
		cli.main(["todo-login"])
	assert exc.value.code not in (0, None)
	assert NOT_CONFIGURED in str(exc.value.code)
