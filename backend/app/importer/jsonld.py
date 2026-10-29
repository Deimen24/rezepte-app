"""schema.org/Recipe extraction from JSON-LD script blocks."""

import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from bs4 import BeautifulSoup

from app.importer.common import RecipeData

LD_TYPE = "application/ld+json"
RECIPE_NODE_KEYS = ("@graph", "mainEntity")
ISO_DURATION = re.compile(
	r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?)?$")
FIRST_INT = re.compile(r"\d+")
BLOCK_END = re.compile(r"<\s*(?:br|/p|/li|/div)\s*/?>", re.I)
NUMBERED = re.compile(r"(?:^|(?<=\s))\d{1,2}[.)]\s+")
HTML_COMMENT = re.compile(r"<!--|-->|<!\[CDATA\[|\]\]>")
NUTRIENT = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:kcal|calories|cal|g)?\s*$",
		      re.I)
NUTRITION_MAX = Decimal("99999.9")
NUTRIENTS = (("kcal", "calories"), ("protein_g", "proteinContent"),
	     ("carbs_g", "carbohydrateContent"), ("fat_g", "fatContent"))


def _is_ld_json(value) -> bool:
	return bool(value) and value.strip().lower().startswith(LD_TYPE)


def _load_json(raw: str):
	text = HTML_COMMENT.sub("", raw).strip()
	if not text:
		return None
	try:
		return json.loads(text, strict=False)
	except ValueError:
		return None


def _is_recipe(node: dict) -> bool:
	types = node.get("@type")
	if isinstance(types, str):
		types = [types]
	if not isinstance(types, list):
		return False
	return any(isinstance(t, str) and
		   t.rsplit("/", 1)[-1].lower() == "recipe" for t in types)


def _find_recipes(node, out: list) -> None:
	if isinstance(node, list):
		for item in node:
			_find_recipes(item, out)
	elif isinstance(node, dict):
		if _is_recipe(node):
			out.append(node)
			return
		for key in RECIPE_NODE_KEYS:
			if key in node:
				_find_recipes(node[key], out)


def clean_text(value) -> str:
	"""Strip tags, unescape entities and collapse whitespace."""
	if not isinstance(value, str):
		return ""
	text = BeautifulSoup(value, "html.parser").get_text(" ")
	return " ".join(text.split())


def _iso_minutes(value: str) -> int | None:
	m = ISO_DURATION.match(value.strip().upper())
	if not m or not any(m.groups()):
		return None
	days, hours, mins = (int(g or 0) for g in m.groups())
	return days * 1440 + hours * 60 + mins


def _to_minutes(value) -> int | None:
	if not isinstance(value, str) or not value.strip():
		return None
	try:
		from app.importer import duration
	except ImportError:
		return _iso_minutes(value)
	return duration.to_minutes(value)


def _servings(value) -> int | None:
	if isinstance(value, list):
		return _servings(value[0]) if value else None
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		return int(value) or None
	if isinstance(value, str):
		m = FIRST_INT.search(value)
		return int(m.group()) if m and int(m.group()) else None
	return None


def _lines(value) -> list[str]:
	if isinstance(value, str):
		return [t for t in (clean_text(p) for p in value.split("\n"))
			if t]
	if isinstance(value, list):
		return [t for item in value for t in _lines(item)]
	return []


def _split_steps(value: str) -> list[str]:
	text = BLOCK_END.sub("\n", value)
	text = BeautifulSoup(text, "html.parser").get_text(" ")
	out = []
	for line in text.split("\n"):
		parts = [line]
		if len(NUMBERED.findall(line)) >= 2:
			parts = NUMBERED.split(line)
		out.extend(t for t in (" ".join(p.split()) for p in parts) if t)
	return out


def _steps(value, out: list[str]) -> None:
	if isinstance(value, str):
		out.extend(_split_steps(value))
	elif isinstance(value, list):
		for item in value:
			_steps(item, out)
	elif isinstance(value, dict):
		if "itemListElement" in value:
			_steps(value["itemListElement"], out)
			return
		text = clean_text(value.get("text") or value.get("name"))
		if text:
			out.append(text)


def _image(value) -> str | None:
	if isinstance(value, str):
		return value.strip() or None
	if isinstance(value, list):
		for item in value:
			url = _image(item)
			if url:
				return url
	if isinstance(value, dict):
		return _image(value.get("url") or value.get("contentUrl"))
	return None


def _nutrient(value) -> Decimal | None:
	"""Accept "250 kcal", "12,5 g" or a bare number; else None."""
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		value = str(value)
	if not isinstance(value, str):
		return None
	m = NUTRIENT.match(value)
	if not m:
		return None
	try:
		amount = Decimal(m.group(1).replace(",", "."))
	except InvalidOperation:
		return None
	if amount < 0 or amount > NUTRITION_MAX:
		return None
	return amount.quantize(Decimal("0.1"), ROUND_HALF_UP)


def _nutrition(value, data: RecipeData) -> None:
	"""Values are per serving as schema.org defines."""
	if isinstance(value, list):
		value = value[0] if value else None
	if not isinstance(value, dict):
		return
	for attr, key in NUTRIENTS:
		setattr(data, attr, _nutrient(value.get(key)))


def _map(node: dict) -> RecipeData:
	data = RecipeData()
	data.title = clean_text(node.get("name"))
	data.intro = clean_text(node.get("description"))
	data.servings = _servings(node.get("recipeYield"))
	data.prep_minutes = _to_minutes(node.get("prepTime"))
	data.cook_minutes = _to_minutes(node.get("cookTime"))
	total = _to_minutes(node.get("totalTime"))
	if data.prep_minutes is None and data.cook_minutes is None \
	   and total is not None:
		data.cook_minutes = total
		data.warnings.append("Nur Gesamtzeit vorhanden, "
				     "als Kochzeit übernommen")
	data.ingredient_lines = _lines(node.get("recipeIngredient"))
	_steps(node.get("recipeInstructions"), data.steps)
	data.image_url = _image(node.get("image"))
	_nutrition(node.get("nutrition"), data)
	if not data.ingredient_lines and not data.steps:
		data.warnings.append("Rezept ohne Zutaten und Schritte")
	return data


def extract(html: str) -> RecipeData | None:
	soup = BeautifulSoup(html, "html.parser")
	recipes: list[dict] = []
	for script in soup.find_all("script", type=_is_ld_json):
		data = _load_json(script.string or script.get_text())
		if data is not None:
			_find_recipes(data, recipes)
	if not recipes:
		return None
	node = next((r for r in recipes if r.get("recipeIngredient")
		     or r.get("recipeInstructions")), recipes[0])
	return _map(node)
