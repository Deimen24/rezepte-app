"""URL import: fetch a page, extract the recipe, build a preview.

Nothing is stored here; saving goes through the normal recipe POST.
"""

from urllib.parse import urljoin, urlsplit

import httpx

from app.importer import heuristic, ingredients, jsonld
from app.importer.common import RecipeData
from app.importer.fetch import SCHEMES, FetchError, fetch_html
from app.models import NAME_LEN
from app.schemas import (
	ImportPreview,
	ImportVersion,
	ParsedIngredient,
	Source,
	StepIn,
)

NO_RECIPE = "Kein Rezept gefunden"
NO_INGREDIENTS = "Keine Zutaten"
NO_STEPS = "Keine Schritte"


def _extract(html: str) -> tuple[RecipeData, str]:
	data = jsonld.extract(html)
	if data is not None and data.is_usable():
		return data, "jsonld"
	return heuristic.extract(html), "heuristic"


def parse_ingredient_lines(lines: list[str]) -> list[ParsedIngredient]:
	return ingredients.parse_lines([l for l in lines if l.strip()])


def _version(data: RecipeData) -> ImportVersion:
	return ImportVersion(
		title=data.title.strip()[:NAME_LEN],
		intro=data.intro.strip(),
		servings=data.servings,
		prep_minutes=data.prep_minutes,
		cook_minutes=data.cook_minutes,
		ingredients=parse_ingredient_lines(data.ingredient_lines),
		steps=[StepIn(text=s) for s in data.steps if s.strip()],
	)


def _image_url(data: RecipeData, base: str) -> str | None:
	if not data.image_url:
		return None
	url = urljoin(base, data.image_url.strip())
	if urlsplit(url).scheme not in SCHEMES:
		return None
	return url


def _warnings(data: RecipeData, version: ImportVersion) -> list[str]:
	warnings = list(data.warnings)
	if not version.ingredients:
		warnings.append(NO_INGREDIENTS)
	if not version.steps:
		warnings.append(NO_STEPS)
	return warnings


def preview(url: str, client: httpx.Client | None = None
	    ) -> ImportPreview:
	"""Raises FetchError when the page cannot be loaded or holds no
	recipe."""
	html, final_url = fetch_html(url, client)
	data, method = _extract(html)
	if not data.is_usable():
		raise FetchError(NO_RECIPE)
	version = _version(data)
	return ImportPreview(
		source=Source(kind="url", url=final_url),
		version=version,
		image_url=_image_url(data, final_url),
		method=method,
		warnings=_warnings(data, version),
	)
