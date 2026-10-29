"""Cookbook page photo -> recipe preview through OCR.

The photo is not stored and the source stays "none": the user names
book and page in the form.
"""

from app.importer import ingredients, ocr
from app.importer.common import RecipeData
from app.importer.ocr import OcrError
from app.models import NAME_LEN
from app.schemas import ImportPreview, ImportVersion, Source, StepIn

CHECK_TEXT = "Text prüfen"
NO_TEXT = "Kein Text erkannt"
NO_INGREDIENTS = "Keine Zutaten"
NO_STEPS = "Keine Schritte"


def _version(data: RecipeData) -> ImportVersion:
	return ImportVersion(
		title=data.title.strip()[:NAME_LEN],
		intro=data.intro.strip(),
		servings=data.servings,
		prep_minutes=data.prep_minutes,
		cook_minutes=data.cook_minutes,
		ingredients=ingredients.parse_lines(data.ingredient_lines),
		steps=[StepIn(text=s) for s in data.steps if s.strip()],
	)


def _warnings(data: RecipeData, version: ImportVersion) -> list[str]:
	warnings = [CHECK_TEXT] + data.warnings
	if not version.ingredients:
		warnings.append(NO_INGREDIENTS)
	if not version.steps:
		warnings.append(NO_STEPS)
	return warnings


def preview_from_image(data: bytes) -> ImportPreview:
	"""Raises ValueError("not an image") for a non-image and OcrError
	when OCR fails or finds no text."""
	text = ocr.run_tesseract(ocr.prepare_image(data))
	if not text.strip():
		raise OcrError(NO_TEXT)
	parsed = ocr.split_text(text)
	version = _version(parsed)
	return ImportPreview(
		source=Source(kind="none"),
		version=version,
		image_url=None,
		method="ocr",
		warnings=_warnings(parsed, version),
	)
