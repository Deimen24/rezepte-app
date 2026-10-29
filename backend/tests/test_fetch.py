"""fetch.py: redirects, limits, content types and SSRF guards, with
httpx.MockTransport and a mocked resolver."""

import httpx
import pytest

from app.importer import fetch
from app.importer.fetch import (
	MAX_BYTES,
	MAX_REDIRECTS,
	FetchError,
	fetch_html,
	fetch_image,
)

PUBLIC_IP = "93.184.216.34"
HTML = {"content-type": "text/html; charset=utf-8"}
PAGE = "<html><body><h1>Suppe</h1></body></html>"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
	monkeypatch.setattr(fetch, "resolve_host", lambda host: [PUBLIC_IP])


def make_client(handler) -> httpx.Client:
	return httpx.Client(transport=httpx.MockTransport(handler))


def html_response(text=PAGE, headers=HTML) -> httpx.Response:
	return httpx.Response(200, headers=headers, content=text.encode())


class Recorder:
	"""Handler that records requests and answers from a table."""

	def __init__(self, responses=None):
		self.urls: list[str] = []
		self.responses = responses or {}

	def __call__(self, request: httpx.Request) -> httpx.Response:
		url = str(request.url)
		self.urls.append(url)
		if url in self.responses:
			return self.responses[url]
		return html_response()


def test_ok_html_returns_text_and_url():
	rec = Recorder()
	text, final = fetch_html("https://example.com/r", make_client(rec))
	assert text == PAGE
	assert final == "https://example.com/r"
	assert rec.urls == ["https://example.com/r"]


def test_sends_user_agent_and_accept():
	seen = {}

	def handler(request):
		seen.update(request.headers)
		return html_response()

	fetch_html("https://example.com/", make_client(handler))
	assert seen["user-agent"] == fetch.USER_AGENT
	assert "text/html" in seen["accept"]


def redirect(target: str) -> httpx.Response:
	return httpx.Response(302, headers={"location": target})


def test_redirect_chain_gives_final_url():
	rec = Recorder({
		"https://example.com/a": redirect("/b"),
		"https://example.com/b": redirect("https://other.org/c"),
	})
	_, final = fetch_html("https://example.com/a", make_client(rec))
	assert final == "https://other.org/c"
	assert rec.urls == ["https://example.com/a", "https://example.com/b",
			    "https://other.org/c"]


def test_too_many_redirects():
	hops = {f"https://example.com/{i}": redirect(f"/{i + 1}")
		for i in range(MAX_REDIRECTS + 1)}
	rec = Recorder(hops)
	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/0", make_client(rec))
	assert err.value.detail == "Zu viele Weiterleitungen"
	assert len(rec.urls) == MAX_REDIRECTS + 1


def test_redirect_to_private_host_is_rejected(monkeypatch):
	table = {"example.com": [PUBLIC_IP], "intern.example": ["10.0.0.5"]}
	monkeypatch.setattr(fetch, "resolve_host", lambda h: table[h])
	rec = Recorder({
		"https://example.com/": redirect("http://intern.example/x")})
	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(rec))
	assert err.value.detail == "Adresse nicht erlaubt"
	assert rec.urls == ["https://example.com/"]


def test_redirect_without_location_is_unreachable():
	rec = Recorder({"https://example.com/": httpx.Response(302)})
	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(rec))
	assert err.value.detail == "Seite nicht erreichbar"


def never_called(request):
	raise AssertionError("request must not be sent: " + str(request.url))


@pytest.mark.parametrize("ip", [
	"10.0.0.1", "172.16.5.5", "192.168.1.1", "127.0.0.1", "0.0.0.0",
	"169.254.169.254", "169.254.10.10", "100.64.0.1", "224.0.0.1",
	"240.0.0.1", "::1", "::", "fc00::1", "fd12::1", "fe80::1",
	"ff02::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
])
def test_resolved_private_address_is_rejected(monkeypatch, ip):
	monkeypatch.setattr(fetch, "resolve_host", lambda h: [ip])
	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(never_called))
	assert err.value.detail == "Adresse nicht erlaubt"


def test_one_private_address_among_public_is_rejected(monkeypatch):
	monkeypatch.setattr(fetch, "resolve_host",
			    lambda h: [PUBLIC_IP, "127.0.0.1"])
	with pytest.raises(FetchError):
		fetch_html("https://example.com/", make_client(never_called))


@pytest.mark.parametrize("url", [
	"http://127.0.0.1/", "http://10.1.2.3:8080/x", "http://[::1]/",
	"http://[fc00::1]/", "http://169.254.169.254/latest/meta-data",
])
def test_literal_private_ip_is_rejected(url):
	with pytest.raises(FetchError) as err:
		fetch_html(url, make_client(never_called))
	assert err.value.detail == "Adresse nicht erlaubt"


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "foo.local",
				  "db.internal", "localhost."])
def test_blocked_hostnames(monkeypatch, host):
	calls = []
	monkeypatch.setattr(fetch, "resolve_host",
			    lambda h: calls.append(h) or [PUBLIC_IP])
	with pytest.raises(FetchError) as err:
		fetch_html(f"http://{host}/", make_client(never_called))
	assert err.value.detail == "Adresse nicht erlaubt"
	assert calls == []


def test_unresolvable_host_is_unreachable(monkeypatch):
	def fail(host):
		raise FetchError("Seite nicht erreichbar")

	monkeypatch.setattr(fetch, "resolve_host", fail)
	with pytest.raises(FetchError) as err:
		fetch_html("https://nope.example/", make_client(never_called))
	assert err.value.detail == "Seite nicht erreichbar"


@pytest.mark.parametrize("url, detail", [
	("ftp://example.com/x", "Nur http und https"),
	("file:///etc/passwd", "Nur http und https"),
	("javascript:alert(1)", "Nur http und https"),
	("example.com/x", "Adresse ungültig"),
	("http:///x", "Adresse ungültig"),
	("", "Adresse ungültig"),
])
def test_bad_scheme_or_url(url, detail):
	with pytest.raises(FetchError) as err:
		fetch_html(url, make_client(never_called))
	assert err.value.detail == detail


def test_wrong_content_type():
	rec = Recorder({"https://example.com/": httpx.Response(
		200, headers={"content-type": "text/plain"}, content=b"x")})
	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(rec))
	assert err.value.detail == "Keine HTML-Seite"


def test_xhtml_is_accepted():
	rec = Recorder({"https://example.com/": httpx.Response(
		200, headers={"content-type": "application/xhtml+xml"},
		content=PAGE.encode())})
	text, _ = fetch_html("https://example.com/", make_client(rec))
	assert text == PAGE


def test_http_error_status_is_unreachable():
	rec = Recorder({"https://example.com/": httpx.Response(
		404, headers=HTML, content=b"gone")})
	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(rec))
	assert err.value.detail == "Seite nicht erreichbar"


def test_body_over_limit_is_cut_off():
	chunk = b"x" * (1024 * 1024)
	yielded = []

	def stream():
		for _ in range(MAX_BYTES // len(chunk) + 2):
			yielded.append(1)
			yield chunk

	def handler(request):
		return httpx.Response(200, headers=HTML, content=stream())

	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(handler))
	assert err.value.detail == "Zu gross (max. 5 MB)"
	assert len(yielded) <= MAX_BYTES // len(chunk) + 1


def test_content_length_over_limit_is_rejected_early():
	def handler(request):
		return httpx.Response(200, headers={
			**HTML, "content-length": str(MAX_BYTES + 1)},
			content=b"")

	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(handler))
	assert err.value.detail == "Zu gross (max. 5 MB)"


def test_timeout():
	def handler(request):
		raise httpx.ReadTimeout("slow")

	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(handler))
	assert err.value.detail == "Zeitüberschreitung"


def test_connect_error_is_unreachable():
	def handler(request):
		raise httpx.ConnectError("refused")

	with pytest.raises(FetchError) as err:
		fetch_html("https://example.com/", make_client(handler))
	assert err.value.detail == "Seite nicht erreichbar"


def test_latin1_charset_header_is_decoded():
	page = "<html><body>Käse mit Öl</body></html>"

	def handler(request):
		return httpx.Response(200, headers={
			"content-type": "text/html; charset=ISO-8859-1"},
			content=page.encode("latin-1"))

	text, _ = fetch_html("https://example.com/", make_client(handler))
	assert text == page


def test_meta_charset_without_header_is_used():
	page = ('<html><head><meta charset="iso-8859-1"></head>'
		"<body>Käse</body></html>")

	def handler(request):
		return httpx.Response(200, headers={
			"content-type": "text/html"},
			content=page.encode("latin-1"))

	text, _ = fetch_html("https://example.com/", make_client(handler))
	assert text == page


def test_no_charset_falls_back_to_utf8():
	page = "<html><body>Käse</body></html>"

	def handler(request):
		return httpx.Response(200, headers={
			"content-type": "text/html"},
			content=page.encode("utf-8"))

	text, _ = fetch_html("https://example.com/", make_client(handler))
	assert text == page


def test_fetch_image_ok():
	def handler(request):
		assert request.headers["accept"] == "image/*"
		return httpx.Response(200, headers={
			"content-type": "image/jpeg"},
			content=b"\xff\xd8\xff")

	data = fetch_image("https://example.com/a.jpg", make_client(handler))
	assert data == b"\xff\xd8\xff"


def test_fetch_image_wrong_type():
	rec = Recorder()
	with pytest.raises(FetchError) as err:
		fetch_image("https://example.com/a.jpg", make_client(rec))
	assert err.value.detail == "Kein Bild"


def test_fetch_image_private_host_rejected(monkeypatch):
	monkeypatch.setattr(fetch, "resolve_host", lambda h: ["192.168.0.9"])
	with pytest.raises(FetchError):
		fetch_image("https://example.com/a.jpg",
			    make_client(never_called))
