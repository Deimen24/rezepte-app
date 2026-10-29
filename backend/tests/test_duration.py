"""ISO 8601 and plain-text durations to minutes."""

import pytest

from app.importer.duration import to_minutes


@pytest.mark.parametrize("value, minutes", [
	("PT30M", 30),
	("PT1H30M", 90),
	("P0DT2H", 120),
	("PT1H", 60),
	("PT90M", 90),
	("P1DT2H", 1560),
	("PT0.5H", 30),
	("PT0,5H", 30),
	("pt45m", 45),
	("PT1H30M15S", 90),
	("PT30S", 1),
	("P1W", 10080),
	("  PT20M  ", 20),
	("30 Min", 30),
	("30 Min.", 30),
	("30Minuten", 30),
	("1 Std 30 Min", 90),
	("1h 30min", 90),
	("1h30", 90),
	("45 minutes", 45),
	("1 hour", 60),
	("2 hrs", 120),
	("1,5 Stunden", 90),
	("1.5 hours", 90),
	("1 ½ Std", 90),
	("½ Stunde", 30),
	("1:30", 90),
	("30", 30),
	("ca. 20 Minuten", 20),
	("Serves 4, 30 min", 30),
	("1 Tag", 1440),
	("90 Sekunden", 2),
	(["PT20M", "PT1H"], 20),
	(("PT25M",), 25),
	(30, 30),
	(12.4, 12),
	(12.5, 13),
])
def test_valid_durations(value, minutes):
	assert to_minutes(value) == minutes


@pytest.mark.parametrize("value", [
	None,
	"",
	"   ",
	"garbage",
	"PT",
	"P",
	"PT0M",
	"P1Y",
	"PTxM",
	"4 Portionen",
	"abc 5 xyz",
	"0 min",
	"10 s",
	0,
	-5,
	True,
	[],
	{},
	{"@type": "Duration"},
	[None],
])
def test_invalid_durations(value):
	assert to_minutes(value) is None
