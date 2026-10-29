"""Split an ingredient line into amount, unit, name and note.

Decisions for ambiguous lines, each covered in tests/test_ingredients.py:
- "2-3 EL", "2 bis 3", "2 to 3": amount 2, note "2–3".
- "2 x 400 g Dosen Tomaten": amount 800, unit g, note "2 x 400 g".
- "Prise Salz": a unit word without a number means amount 1.
- "1 (14 oz) can chickpeas": amount 1, unit Dose, note "14 oz".
- "ca.", "etwa", "approx." before the number are dropped.
- Note takes text in parentheses, text after the first comma (a decimal
  comma does not count) and trailing phrases such as "nach Belieben",
  "zum Servieren", "to taste", "optional".
- A number the database cannot hold (Numeric(10,3)) or "1/0" is left in
  the name.
- The name is never empty; the raw line is the fallback.
"""

import re
import unicodedata
from decimal import Decimal
from fractions import Fraction

from app.models import NAME_LEN, UNIT_LEN
from app.schemas import ParsedIngredient, amount_to_str

# canonical unit -> aliases, matched case-insensitively
UNITS = {
	"g": ("g", "gr", "gramm", "gram", "grams"),
	"kg": ("kg", "kilo", "kilogramm", "kilogram", "kilograms"),
	"mg": ("mg", "milligramm", "milligram"),
	"ml": ("ml", "milliliter", "millilitre", "milliliters", "millilitres"),
	"cl": ("cl",),
	"dl": ("dl", "deziliter"),
	"l": ("l", "lt", "ltr", "liter", "litre", "liters", "litres"),
	"EL": ("el", "essl", "esslöffel", "tbsp", "tbs", "tablespoon",
	       "tablespoons"),
	"TL": ("tl", "teelöffel", "tsp", "teaspoon", "teaspoons"),
	"Prise": ("prise", "prisen", "pinch", "pinches"),
	"Stück": ("stk", "stück", "stücke", "st", "piece", "pieces", "pcs",
		  "pc"),
	"Bund": ("bund", "bunch", "bunches"),
	"Zehe": ("zehe", "zehen", "clove", "cloves"),
	"Dose": ("dose", "dosen", "can", "cans", "tin", "tins"),
	"Pck": ("pck", "päckchen", "packung", "packungen", "pkg", "pk",
		"package", "packages", "packet", "packets"),
	"Tasse": ("tasse", "tassen", "cup", "cups"),
	"Scheibe": ("scheibe", "scheiben", "slice", "slices"),
	"Blatt": ("blatt", "blätter", "leaf", "leaves"),
	"Würfel": ("würfel", "cube", "cubes"),
	"Becher": ("becher",),
	"Glas": ("glas", "gläser", "jar", "jars"),
	"Flasche": ("flasche", "flaschen", "bottle", "bottles"),
	"oz": ("oz", "ounce", "ounces"),
	"lb": ("lb", "lbs", "pound", "pounds"),
	"Msp": ("msp", "messerspitze", "messerspitzen"),
}
ALIASES = {alias: unit for unit, aliases in UNITS.items() for alias in aliases}
# the only case-sensitive aliases: T = tablespoon, t = teaspoon
CASE_ALIASES = {"T": "EL", "t": "TL"}

FRACTION_CHARS = "½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
AMOUNT_STEP = Decimal("0.001")
AMOUNT_MAX = Decimal("9999999.999")
ONE = Decimal(1)
EDGE_CHARS = " \t.,;:-–—"

# "1 ½", "1½", "1 1/2", "1/2", "1,5", "1.5", "2", "¾"
NUMBER = (
	rf"(?:\d+\s*[{FRACTION_CHARS}]|\d+\s+\d+/\d+|\d+/\d+"
	rf"|\d+(?:[.,]\d+)?|[{FRACTION_CHARS}])"
)
PART_RE = re.compile(rf"\d+/\d+|\d+(?:[.,]\d+)?|[{FRACTION_CHARS}]")
AMOUNT_RE = re.compile(
	rf"^(?P<first>{NUMBER})"
	rf"(?:\s*(?:-|–|—|bis|to)\s*(?P<last>{NUMBER})"
	rf"|\s*[x×]\s*(?P<factor>{NUMBER}))?"
	r"(?=\s|$|[^\W\d_])",
	re.IGNORECASE,
)
BULLET_RE = re.compile(r"^[-•*·–]\s*")
APPROX_RE = re.compile(
	r"^(?:ca\.?|circa|etwa|ungefähr|approx\.?|about|around|roughly)\s+",
	re.IGNORECASE,
)
COMMA_RE = re.compile(r",(?!\d)")
PAREN_RE = re.compile(r"\s*\(([^()]*)\)")
UNIT_RE = re.compile(r"^([^\W\d_]+)\.?(?=\s|$)")
OF_RE = re.compile(r"^(?:of|von)\s+", re.IGNORECASE)
PHRASE_RE = re.compile(
	r"^(?P<name>.*?\S)\s+(?P<note>(?:nach|zum|zur|für|to|for|if|as)\s+\S.*"
	r"|(?:optional|wahlweise)\b.*)$",
	re.IGNORECASE,
)


def to_fraction(text: str) -> Fraction:
	"""Sum the parts of "1 ½", "1 1/2", "1,5" or "¾"."""
	total = Fraction(0)
	for part in PART_RE.findall(text):
		if part in FRACTION_CHARS:
			value = Fraction(unicodedata.numeric(part))
			total += value.limit_denominator(100)
		elif "/" in part:
			num, den = part.split("/")
			total += Fraction(int(num), int(den))
		else:
			total += Fraction(Decimal(part.replace(",", ".")))
	return total


def to_decimal(value: Fraction) -> Decimal | None:
	"""Round to 3 decimals; None when Numeric(10,3) cannot hold it."""
	dec = Decimal(value.numerator) / Decimal(value.denominator)
	dec = dec.quantize(AMOUNT_STEP)
	if dec > AMOUNT_MAX:
		return None
	if dec == dec.to_integral_value():
		return dec.quantize(ONE)
	return dec.normalize()


def fmt(value: Fraction) -> str:
	return amount_to_str(to_decimal(value)) or ""


def resolve_amount(m: re.Match, unit: str) -> tuple[Decimal | None, str]:
	"""Amount and the note of a range ("2–3") or product ("2 x 400 g")."""
	first = to_fraction(m["first"])
	if m["factor"]:
		factor = to_fraction(m["factor"])
		note = f"{fmt(first)} x {fmt(factor)} {unit}".rstrip()
		return to_decimal(first * factor), note
	if m["last"]:
		last = to_fraction(m["last"])
		return to_decimal(first), f"{fmt(first)}–{fmt(last)}"
	return to_decimal(first), ""


def take_unit(text: str) -> tuple[str, str]:
	"""Canonical unit at the start of text and the rest, or "" and text."""
	m = UNIT_RE.match(text)
	if not m:
		return "", text
	word = m.group(1)
	unit = CASE_ALIASES.get(word) or ALIASES.get(word.lower())
	if not unit:
		return "", text
	return unit, OF_RE.sub("", text[m.end():].lstrip())


def split_amount_unit(head: str) -> tuple[Decimal | None, str, str, str]:
	"""Amount, amount note, unit and the remaining text of a line head."""
	m = AMOUNT_RE.match(head)
	rest = head[m.end():].lstrip() if m else head
	unit, rest = take_unit(rest)
	if m is None:
		return (ONE if unit else None), "", unit, rest
	try:
		amount, note = resolve_amount(m, unit)
	except ZeroDivisionError:
		amount = None
	if amount is None:
		return None, "", "", head
	return amount, note, unit, rest


def split_phrase(text: str) -> tuple[str, str]:
	"""Move a trailing "zum Servieren", "to taste", ... into the note."""
	m = PHRASE_RE.match(text)
	if not m:
		return text, ""
	return m["name"], m["note"]


def parse_line(raw: str) -> ParsedIngredient:
	raw = raw.strip()
	if not raw:
		raise ValueError("empty ingredient line")
	text = APPROX_RE.sub("", BULLET_RE.sub("", raw))
	parts = COMMA_RE.split(text, maxsplit=1)
	tail = parts[1] if len(parts) > 1 else ""
	notes = PAREN_RE.findall(parts[0])
	head = PAREN_RE.sub("", parts[0]).strip()
	amount, amount_note, unit, rest = split_amount_unit(head)
	name, phrase = split_phrase(rest)
	name = name.strip(EDGE_CHARS) or raw
	pieces = [amount_note, *notes, phrase, tail]
	pieces = [p.strip(EDGE_CHARS) for p in pieces]
	note = "; ".join(p for p in pieces if p)
	return ParsedIngredient(
		amount=amount,
		unit=unit[:UNIT_LEN],
		name=name[:NAME_LEN],
		note=note[:NAME_LEN],
		raw=raw,
	)


def parse_lines(lines: list[str]) -> list[ParsedIngredient]:
	"""One ParsedIngredient per non-blank line, in order."""
	return [parse_line(line) for line in lines if line and line.strip()]
