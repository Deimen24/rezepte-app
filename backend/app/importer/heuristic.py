"""Fallback extraction from HTML pages without structured recipe data."""

import re

from bs4 import BeautifulSoup, Tag

from app.importer.common import RecipeData

DROP_TAGS = ("script", "style", "noscript", "template", "nav", "footer",
	     "header")
HEADINGS = ("h1", "h2", "h3", "h4")
LABEL_TAGS = ("strong", "b", "p")
LIST_TAGS = ("ul", "ol")
TITLE_SEPARATORS = (" | ", " - ", " – ")
MAX_INGREDIENT_LEN = 300
MIN_QUANTITY_ITEMS = 3
MAX_LABEL_LEN = 40

INGREDIENTS_RE = re.compile(r"zutaten|ingredients", re.I)
STEPS_RE = re.compile(r"zubereitung|anleitung|instructions|method|"
		      r"directions|so geht|schritt", re.I)
SERVINGS_RE = re.compile(r"(\d+)\s*(?:Portionen|Personen|Stück|"
			 r"servings|serves)|serves\s*(\d+)", re.I)
QUANTITY_RE = re.compile(r"^\s*[\d¼½¾⅓⅔⅛⅜⅝⅞]")

TIME_UNIT = r"(?:std\.?|stunden?|h\b|hours?|hrs?|min\.?|minuten|minutes?|mins?)"
TIME_SPAN = (r"(\d+\s*" + TIME_UNIT +
	     r"(?:\s*(?:und|and)?\s*\d+\s*" + TIME_UNIT + r")?)")
PREP_RE = re.compile(r"(?:zubereitung(?:szeit)?|vorbereitung(?:szeit)?|"
		     r"arbeitszeit|prep(?:aration)?(?:\s*time)?)\s*:?\s*"
		     r"(?:ca\.?\s*)?" + TIME_SPAN, re.I)
COOK_RE = re.compile(r"(?:koch-?\s*(?:/|und|&|oder)?\s*backzeit|kochzeit|"
		     r"backzeit|garzeit|cook(?:ing)?(?:\s*time)?|"
		     r"bak(?:e|ing)(?:\s*time)?)\s*:?\s*(?:ca\.?\s*)?"
		     + TIME_SPAN, re.I)
HOURS_RE = re.compile(r"(\d+)\s*(?:std|stunden?|h\b|hours?|hrs?)", re.I)
MINUTES_RE = re.compile(r"(\d+)\s*(?:min|minuten|minutes?|mins?)", re.I)


def _collapse(text: str) -> str:
	return " ".join(text.split())


def _text(tag: Tag) -> str:
	return _collapse(tag.get_text(" "))


def _meta(soup: BeautifulSoup, key: str) -> str:
	for tag in soup.find_all("meta"):
		name = (tag.get("property") or tag.get("name") or "").lower()
		if name == key and tag.get("content"):
			return _collapse(tag["content"])
	return ""


def _strip_site(title: str) -> str:
	for sep in TITLE_SEPARATORS:
		head, found, _ = title.partition(sep)
		if found and head.strip():
			return head.strip()
	return title


def _title(soup: BeautifulSoup) -> str:
	title = _meta(soup, "og:title")
	if title:
		return title
	h1 = soup.find("h1")
	if h1 is not None and _text(h1):
		return _text(h1)
	if soup.title is not None and soup.title.string:
		return _strip_site(_collapse(soup.title.string))
	return ""


def _servings(text: str) -> int | None:
	m = SERVINGS_RE.search(text)
	if not m:
		return None
	return int(m.group(1) or m.group(2)) or None


def _text_minutes(span: str) -> int | None:
	try:
		from app.importer import duration
		mins = duration.to_minutes(span)
		if mins is not None:
			return mins
	except (ImportError, ValueError):
		pass
	hours = HOURS_RE.search(span)
	mins = MINUTES_RE.search(span)
	if not hours and not mins:
		return None
	return (int(hours.group(1)) * 60 if hours else 0) + \
	       (int(mins.group(1)) if mins else 0)


def _time(text: str, pattern: re.Pattern) -> int | None:
	m = pattern.search(text)
	return _text_minutes(m.group(1)) if m else None


def _is_label(tag: Tag, pattern: re.Pattern) -> bool:
	"""Headings match anywhere, bold or paragraph labels only when short."""
	text = _text(tag)
	if tag.name not in HEADINGS and len(text) > MAX_LABEL_LEN:
		return False
	return bool(pattern.search(text))


def _find_label(soup: BeautifulSoup, pattern: re.Pattern) -> Tag | None:
	"""Real headings win over bold or paragraph labels."""
	for names in (HEADINGS, LABEL_TAGS):
		for tag in soup.find_all(names):
			if _is_label(tag, pattern):
				return tag
	return None


def _items(lst: Tag, limit: int | None = None) -> list[str]:
	out = []
	for li in lst.find_all("li"):
		text = _text(li)
		if text and (limit is None or len(text) <= limit):
			out.append(text)
	return out


def _quantity_count(lst: Tag) -> int:
	return sum(1 for t in _items(lst, MAX_INGREDIENT_LEN)
		   if QUANTITY_RE.match(t))


def _guess_ingredient_list(soup: BeautifulSoup) -> Tag | None:
	best, score = None, MIN_QUANTITY_ITEMS - 1
	for lst in soup.find_all(LIST_TAGS):
		count = _quantity_count(lst)
		if count > score:
			best, score = lst, count
	return best


def _ingredients(soup: BeautifulSoup, data: RecipeData) -> Tag | None:
	label = _find_label(soup, INGREDIENTS_RE)
	lst = label.find_next(LIST_TAGS) if label is not None else None
	if lst is None:
		lst = _guess_ingredient_list(soup)
		if lst is None:
			data.warnings.append("Zutaten nicht gefunden")
			return None
		data.warnings.append("Zutaten geraten")
	data.ingredient_lines = _items(lst, MAX_INGREDIENT_LEN)
	return lst


def _steps_after_label(label: Tag, used: Tag | None) -> list[str]:
	"""First <ol> before the next heading, else the paragraphs."""
	paras = []
	for tag in label.find_all_next(HEADINGS + ("ol", "p")):
		if tag.name in HEADINGS:
			break
		if tag.name == "ol" and tag is not used:
			return _items(tag)
		if tag.name == "p" and tag is not label:
			text = _text(tag)
			if text:
				paras.append(text)
	return paras


def _longest_ol(soup: BeautifulSoup, used: Tag | None) -> list[str]:
	best: list[str] = []
	for ol in soup.find_all("ol"):
		if ol is not used and len(_items(ol)) > len(best):
			best = _items(ol)
	return best


def _steps(soup: BeautifulSoup, data: RecipeData, used: Tag | None) -> None:
	label = _find_label(soup, STEPS_RE)
	if label is not None:
		data.steps = _steps_after_label(label, used)
		if data.steps:
			return
	data.steps = _longest_ol(soup, used)
	data.warnings.append("Schritte geraten" if data.steps
			     else "Schritte nicht gefunden")


def extract(html: str) -> RecipeData:
	soup = BeautifulSoup(html, "html.parser")
	data = RecipeData()
	data.title = _title(soup)
	data.intro = _meta(soup, "og:description") or \
		     _meta(soup, "description")
	data.image_url = _meta(soup, "og:image") or None
	for tag in soup.find_all(DROP_TAGS):
		tag.decompose()
	text = _collapse(soup.get_text(" "))
	data.servings = _servings(text)
	data.prep_minutes = _time(text, PREP_RE)
	data.cook_minutes = _time(text, COOK_RE)
	if not data.title:
		data.warnings.append("Titel nicht gefunden")
	used = _ingredients(soup, data)
	_steps(soup, data, used)
	return data
