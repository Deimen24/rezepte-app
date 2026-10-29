"""Fetch pages and images from the web with SSRF guards.

Every hop of a redirect chain is checked again: scheme, hostname and
all resolved addresses. Bodies are streamed and cut off at a limit.
"""

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

TIMEOUT = 10.0
MAX_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = "Rezepte-App/1.0 (+private)"

SCHEMES = ("http", "https")
HTML_TYPES = ("text/html", "application/xhtml+xml")
HTML_ACCEPT = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"
IMAGE_ACCEPT = "image/*"
BLOCKED_HOSTS = ("localhost",)
BLOCKED_SUFFIXES = (".local", ".internal")
BLOCKED_NETS = (
	ipaddress.ip_network("169.254.169.254/32"),
	ipaddress.ip_network("100.64.0.0/10"),
)
META_CHARSET = re.compile(rb'<meta[^>]+charset=["\']?([\w-]+)', re.I)
SNIFF_BYTES = 2048

INVALID = "Adresse ungültig"
SCHEME = "Nur http und https"
FORBIDDEN = "Adresse nicht erlaubt"
UNREACHABLE = "Seite nicht erreichbar"
TIMED_OUT = "Zeitüberschreitung"
TOO_LARGE = "Zu gross (max. {} MB)"
NOT_HTML = "Keine HTML-Seite"
NOT_IMAGE = "Kein Bild"
TOO_MANY_REDIRECTS = "Zu viele Weiterleitungen"


class FetchError(ValueError):
	"""Carries a short German message for the API response."""

	def __init__(self, detail: str):
		super().__init__(detail)
		self.detail = detail


def resolve_host(host: str) -> list[str]:
	"""All addresses a hostname resolves to; tests replace this."""
	try:
		infos = socket.getaddrinfo(host, None)
	except socket.gaierror:
		raise FetchError(UNREACHABLE)
	return sorted({info[4][0] for info in infos})


def _address_blocked(text: str) -> bool:
	try:
		addr = ipaddress.ip_address(text)
	except ValueError:
		return True
	if addr.version == 6 and addr.ipv4_mapped is not None:
		addr = addr.ipv4_mapped
	if (addr.is_private or addr.is_loopback or addr.is_link_local
	    or addr.is_multicast or addr.is_reserved
	    or addr.is_unspecified):
		return True
	return any(addr in net for net in BLOCKED_NETS)


def _check_host(host: str) -> None:
	name = host.lower().rstrip(".")
	if name in BLOCKED_HOSTS or name.endswith(BLOCKED_SUFFIXES):
		raise FetchError(FORBIDDEN)
	try:
		ipaddress.ip_address(name)
		addrs = [name]
	except ValueError:
		addrs = resolve_host(name)
	if not addrs or any(_address_blocked(a) for a in addrs):
		raise FetchError(FORBIDDEN)


def check_url(url: str) -> None:
	"""Reject anything but http(s) to a public host."""
	try:
		parts = urlsplit(url)
	except ValueError:
		raise FetchError(INVALID)
	if not parts.scheme:
		raise FetchError(INVALID)
	if parts.scheme not in SCHEMES:
		raise FetchError(SCHEME)
	try:
		host = parts.hostname
	except ValueError:
		raise FetchError(INVALID)
	if not host:
		raise FetchError(INVALID)
	_check_host(host)


def _content_type(resp: httpx.Response) -> str:
	ctype = resp.headers.get("content-type", "")
	return ctype.split(";")[0].strip().lower()


def _read_body(resp: httpx.Response, max_bytes: int) -> bytes:
	limit = TOO_LARGE.format(max_bytes // (1024 * 1024))
	length = resp.headers.get("content-length")
	if length and length.isdigit() and int(length) > max_bytes:
		raise FetchError(limit)
	chunks = []
	size = 0
	for chunk in resp.iter_bytes():
		size += len(chunk)
		if size > max_bytes:
			raise FetchError(limit)
		chunks.append(chunk)
	return b"".join(chunks)


def _send(client: httpx.Client, url: str, accept: str) -> httpx.Response:
	req = client.build_request("GET", url, headers={
		"User-Agent": USER_AGENT, "Accept": accept})
	return client.send(req, stream=True)


def _get(url: str, client: httpx.Client | None, accept: str,
	 type_ok, type_error: str, max_bytes: int
	 ) -> tuple[bytes, str, httpx.Response]:
	"""Follow redirects by hand, checking every hop, and return the
	body, the final URL and the (closed) response."""
	own = client is None
	if own:
		client = httpx.Client(timeout=TIMEOUT)
	try:
		for _ in range(MAX_REDIRECTS + 1):
			check_url(url)
			resp = _send(client, url, accept)
			try:
				if resp.is_redirect:
					target = resp.headers.get("location")
					if not target:
						raise FetchError(UNREACHABLE)
					url = urljoin(url, target)
					continue
				if not resp.is_success:
					raise FetchError(UNREACHABLE)
				if not type_ok(_content_type(resp)):
					raise FetchError(type_error)
				body = _read_body(resp, max_bytes)
			finally:
				resp.close()
			return body, url, resp
		raise FetchError(TOO_MANY_REDIRECTS)
	except httpx.TimeoutException:
		raise FetchError(TIMED_OUT)
	except httpx.HTTPError:
		raise FetchError(UNREACHABLE)
	finally:
		if own:
			client.close()


def _decode(body: bytes, resp: httpx.Response) -> str:
	encoding = resp.charset_encoding
	if encoding is None:
		found = META_CHARSET.search(body[:SNIFF_BYTES])
		encoding = found.group(1).decode("ascii") if found else "utf-8"
	try:
		return body.decode(encoding, errors="replace")
	except LookupError:
		return body.decode("utf-8", errors="replace")


def fetch_html(url: str, client: httpx.Client | None = None
	       ) -> tuple[str, str]:
	"""Return (html, final_url)."""
	body, final, resp = _get(url, client, HTML_ACCEPT,
				 lambda t: t in HTML_TYPES, NOT_HTML,
				 MAX_BYTES)
	return _decode(body, resp), final


def fetch_image(url: str, client: httpx.Client | None = None) -> bytes:
	body, _, _ = _get(url, client, IMAGE_ACCEPT,
			  lambda t: t.startswith("image/"), NOT_IMAGE,
			  MAX_IMAGE_BYTES)
	return body
