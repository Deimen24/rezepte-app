"""OCR of a photographed cookbook page and splitting of the raw text.

Section rules, each covered in tests/test_ocr.py:
- Keyword lines ("Zutaten", "Zubereitung", ...) are short lines matching
  the heuristic importer's patterns; a time line ("Zubereitungszeit:
  30 Min") is not a keyword line.
- Title: first short line before the first keyword line.
- Without a steps keyword, the ingredient list ends at the first line
  that looks like a step (long, or numbered).
- Without an ingredients keyword, lines starting with an amount are
  ingredients; with no keywords at all, the rest are steps split at
  blank lines.
- Steps: a numbered line ("1.", "1)", "Schritt 1") or a blank line
  starts a new step, other lines continue the current one.
"""

import re
import subprocess
from io import BytesIO

from app import images
from app.importer import duration
from app.importer.common import RecipeData
from app.importer.heuristic import (
	COOK_RE,
	INGREDIENTS_RE,
	MAX_LABEL_LEN,
	PREP_RE,
	QUANTITY_RE,
	STEPS_RE,
)

TESSERACT = "tesseract"
LANGS = "deu+eng"
PSM = "4"
TIMEOUT = 60
MAX_SIDE = 2500
MAX_TITLE_LEN = 80
MAX_INGREDIENT_LEN = 60

NOT_INSTALLED = "Texterkennung nicht installiert"
TIMED_OUT = "Zeitüberschreitung"
FAILED = "Texterkennung fehlgeschlagen"
NO_TITLE = "Titel nicht gefunden"
GUESSED_INGREDIENTS = "Zutaten geraten"
GUESSED_STEPS = "Schritte geraten"

# "Zwie-\nbeln" -> "Zwiebeln"; a capital after the hyphen is a compound
HYPHEN_RE = re.compile(r"(?<=\w)-\n(?=[a-zäöüß])")
FRACTION_SLASH_RE = re.compile(r"(?<=\d)⁄(?=\d)")
SPACES_RE = re.compile(r"[ \t]+")
STEP_START_RE = re.compile(r"^(?:\d{1,2}\s*[.)]|schritt\s*\d*\s*[.:)]?)\s*",
			   re.I)
# narrower than the heuristic's: "2 Stück Eier" is not a serving count
SERVINGS_RE = re.compile(r"(\d+)\s*(?:Portionen|Personen|servings|people)"
			 r"|serves\s*(\d+)", re.I)


class OcrError(ValueError):
	"""Carries a short German message for the API response."""

	def __init__(self, detail: str):
		super().__init__(detail)
		self.detail = detail


def prepare_image(data: bytes) -> bytes:
	"""Grayscale PNG, longest side at most MAX_SIDE, never upscaled.

	Raises ValueError("not an image") for anything Pillow rejects.
	"""
	img = images._fit(images._open(data).convert("L"), MAX_SIDE)
	buf = BytesIO()
	img.save(buf, "PNG")
	return buf.getvalue()


def run_tesseract(image: bytes) -> str:
	cmd = [TESSERACT, "stdin", "stdout", "-l", LANGS, "--psm", PSM]
	try:
		proc = subprocess.run(cmd, input=image, capture_output=True,
				      timeout=TIMEOUT)
	except FileNotFoundError:
		raise OcrError(NOT_INSTALLED)
	except subprocess.TimeoutExpired:
		raise OcrError(TIMED_OUT)
	if proc.returncode != 0:
		raise OcrError(FAILED)
	return proc.stdout.decode("utf-8", "replace")


def clean_lines(text: str) -> list[str]:
	"""Stripped lines; blank lines are kept as "" (paragraph breaks)."""
	text = HYPHEN_RE.sub("", text.replace("\r\n", "\n"))
	text = FRACTION_SLASH_RE.sub("/", text)
	lines = [SPACES_RE.sub(" ", l).strip() for l in text.split("\n")]
	while lines and not lines[-1]:
		lines.pop()
	return lines


def _is_time_line(line: str) -> bool:
	return bool(PREP_RE.search(line) or COOK_RE.search(line))


def _keyword(line: str) -> str | None:
	"""'ingredients', 'steps' or None for a normal line; a numbered
	line ("Schritt 1 ...") is a step, not a label."""
	if not line or len(line) > MAX_LABEL_LEN or _is_time_line(line):
		return None
	if STEP_START_RE.match(line):
		return None
	if INGREDIENTS_RE.search(line):
		return "ingredients"
	if STEPS_RE.search(line):
		return "steps"
	return None


def _sections(lines: list[str]) -> tuple[dict[str, list[str]], set[str]]:
	"""Lines grouped by the keyword line before them, and the keywords
	seen."""
	out: dict[str, list[str]] = {"head": [], "ingredients": [],
				     "steps": []}
	found: set[str] = set()
	current = "head"
	for line in lines:
		key = _keyword(line)
		if key is not None:
			current = key
			found.add(key)
			continue
		out[current].append(line)
	return out, found


def _is_step_like(line: str) -> bool:
	return len(line) > MAX_INGREDIENT_LEN or bool(STEP_START_RE.match(line))


def merge_steps(lines: list[str]) -> list[str]:
	steps: list[str] = []
	open_step = False
	for line in lines:
		if not line:
			open_step = False
			continue
		m = STEP_START_RE.match(line)
		if m:
			line = line[m.end():]
			open_step = False
		if open_step:
			steps[-1] = f"{steps[-1]} {line}".strip()
		elif line:
			steps.append(line)
			open_step = True
	return [s for s in steps if s]


def _servings(text: str) -> int | None:
	m = SERVINGS_RE.search(text)
	if not m:
		return None
	return int(m.group(1) or m.group(2)) or None


def _minutes(text: str, pattern: re.Pattern) -> int | None:
	m = pattern.search(text)
	return duration.to_minutes(m.group(1)) if m else None


def _is_meta(line: str) -> bool:
	return _is_time_line(line) or bool(SERVINGS_RE.search(line))


def _head(head: list[str], data: RecipeData) -> list[str]:
	"""Set the title, return the remaining content lines of the head."""
	rest: list[str] = []
	for line in head:
		if not data.title and line and len(line) < MAX_TITLE_LEN:
			data.title = line
		elif not _is_meta(line):
			rest.append(line)
	if not data.title:
		data.warnings.append(NO_TITLE)
	return rest


def _split_guessed(lines: list[str]) -> tuple[list[str], list[str]]:
	"""Amount lines are ingredients, the rest is prose."""
	amounts = [l for l in lines if QUANTITY_RE.match(l)]
	prose = [l for l in lines if not QUANTITY_RE.match(l)]
	return amounts, prose


def _cut_steps(lines: list[str]) -> tuple[list[str], list[str]]:
	"""Ingredients until the first step-like line, the rest are steps."""
	for i, line in enumerate(lines):
		if line and _is_step_like(line):
			return lines[:i], lines[i:]
	return lines, []


def _fill(sec: dict[str, list[str]], found: set[str],
	  data: RecipeData) -> None:
	rest = _head(sec["head"], data)
	ing, steps = sec["ingredients"], sec["steps"]
	if "ingredients" in found and "steps" not in found:
		ing, steps = _cut_steps(ing)
	if "ingredients" not in found:
		ing, rest = _split_guessed(rest)
		if ing:
			data.warnings.append(GUESSED_INGREDIENTS)
		if "steps" not in found:
			steps, rest = rest, []
	if "steps" not in found and steps:
		data.warnings.append(GUESSED_STEPS)
	data.intro = " ".join(l for l in rest if l)
	data.ingredient_lines = [l for l in ing if l]
	data.steps = merge_steps(steps)


def split_text(text: str) -> RecipeData:
	lines = clean_lines(text)
	data = RecipeData()
	sec, found = _sections(lines)
	_fill(sec, found, data)
	flat = " ".join(lines)
	data.servings = _servings(flat)
	data.prep_minutes = _minutes(flat, PREP_RE)
	data.cook_minutes = _minutes(flat, COOK_RE)
	return data
