"""Durations in minutes from ISO 8601 ("PT1H30M") or text ("1 Std 30 Min").

Text rules: "1h30" counts the bare 30 as minutes after an hour; a bare
number alone ("30") is minutes; any other bare number or unknown unit
word ("4 Portionen") is ignored. "1:30" is hours:minutes.
"""

import re
import unicodedata

NUMBER = r"\d+(?:[.,]\d+)?"
FRACTION_CHARS = "½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"

ISO_RE = re.compile(
	rf"^P(?:(?P<w>{NUMBER})W)?(?:(?P<d>{NUMBER})D)?"
	rf"(?:T(?:(?P<h>{NUMBER})H)?(?:(?P<m>{NUMBER})M)?"
	rf"(?:(?P<s>{NUMBER})S)?)?$",
	re.IGNORECASE,
)
ISO_FACTORS = {"w": 10080, "d": 1440, "h": 60, "m": 1, "s": 1 / 60}

CLOCK_RE = re.compile(r"^(\d+):(\d{2})$")
TEXT_RE = re.compile(
	rf"(?:(?P<int>{NUMBER})\s*(?P<frac>[{FRACTION_CHARS}])?"
	rf"|(?P<lone>[{FRACTION_CHARS}]))"
	r"\s*(?P<unit>[^\W\d_]*)"
)
TEXT_UNITS = {
	1440: ("d", "day", "days", "tag", "tage", "tagen"),
	60: ("h", "hr", "hrs", "hour", "hours", "std", "stdn", "stunde",
	     "stunden"),
	1: ("m", "min", "mins", "minute", "minutes", "minuten"),
	1 / 60: ("s", "sec", "secs", "second", "seconds", "sek", "sekunde",
		 "sekunden"),
}
TEXT_FACTORS = {w: f for f, words in TEXT_UNITS.items() for w in words}


def number(text: str) -> float:
	return float(text.replace(",", "."))


def iso_minutes(text: str) -> float | None:
	m = ISO_RE.match(text)
	if not m or not any(m.groupdict().values()):
		return None
	return sum(number(v) * ISO_FACTORS[k]
		   for k, v in m.groupdict().items() if v)


def text_value(m: re.Match) -> float:
	value = number(m["int"]) if m["int"] else 0.0
	frac = m["frac"] or m["lone"]
	if frac:
		value += unicodedata.numeric(frac)
	return value


def text_minutes(text: str) -> float | None:
	m = CLOCK_RE.match(text)
	if m:
		return int(m.group(1)) * 60 + int(m.group(2))
	matches = list(TEXT_RE.finditer(text))
	total = 0.0
	after_hours = False
	for m in matches:
		unit = m["unit"].lower()
		if unit:
			factor = TEXT_FACTORS.get(unit)
		else:
			factor = 1 if after_hours or len(matches) == 1 else None
		if factor is None:
			continue
		total += text_value(m) * factor
		after_hours = factor == 60
	return total if matches else None


def to_minutes(value) -> int | None:
	"""Whole minutes, or None for nothing usable; a list means its first."""
	if isinstance(value, (list, tuple)):
		return to_minutes(value[0]) if value else None
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		minutes = float(value)
	elif isinstance(value, str):
		text = value.strip()
		minutes = iso_minutes(text)
		if minutes is None:
			minutes = text_minutes(text)
	else:
		return None
	if minutes is None or minutes <= 0:
		return None
	return int(minutes + 0.5) or None
