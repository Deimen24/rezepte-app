"""Ingredient line parser: amounts, units, names and notes in DE/EN."""

from decimal import Decimal

import pytest

from app.importer.ingredients import UNITS, parse_line, parse_lines
from app.models import NAME_LEN, UNIT_LEN

D = Decimal


@pytest.mark.parametrize("raw, amount, unit, name, note", [
	("250 g Mehl", D("250"), "g", "Mehl", ""),
	("1,5 dl Rahm", D("1.5"), "dl", "Rahm", ""),
	("1/2 TL Salz", D("0.5"), "TL", "Salz", ""),
	("½ Bund Petersilie, gehackt", D("0.5"), "Bund", "Petersilie",
	 "gehackt"),
	("1 ½ Tassen Reis", D("1.5"), "Tasse", "Reis", ""),
	("1½ Tassen Reis", D("1.5"), "Tasse", "Reis", ""),
	("1 1/2 cups milk", D("1.5"), "Tasse", "milk", ""),
	("⅓ cup sugar", D("0.333"), "Tasse", "sugar", ""),
	("¾ l Brühe", D("0.75"), "l", "Brühe", ""),
	("2-3 EL Olivenöl", D("2"), "EL", "Olivenöl", "2–3"),
	("2–3 EL Olivenöl", D("2"), "EL", "Olivenöl", "2–3"),
	("2 - 3 EL Olivenöl", D("2"), "EL", "Olivenöl", "2–3"),
	("2 bis 3 Äpfel", D("2"), "", "Äpfel", "2–3"),
	("2 to 3 apples", D("2"), "", "apples", "2–3"),
	("1,5-2 l Wasser", D("1.5"), "l", "Wasser", "1.5–2"),
	("2 Zehen Knoblauch (gepresst)", D("2"), "Zehe", "Knoblauch",
	 "gepresst"),
	("2 cloves garlic, minced", D("2"), "Zehe", "garlic", "minced"),
	("Salz", None, "", "Salz", ""),
	("Pfeffer aus der Mühle", None, "", "Pfeffer aus der Mühle", ""),
	("1 Prise Muskat", D("1"), "Prise", "Muskat", ""),
	("Prise Salz", D("1"), "Prise", "Salz", ""),
	("2 x 400 g Dosen Tomaten", D("800"), "g", "Dosen Tomaten",
	 "2 x 400 g"),
	("2x400g Tomaten", D("800"), "g", "Tomaten", "2 x 400 g"),
	("ca. 200 g Feta", D("200"), "g", "Feta", ""),
	("etwa 1 l Wasser", D("1"), "l", "Wasser", ""),
	("approx. 2 cups sugar", D("2"), "Tasse", "sugar", ""),
	("1 kleine Zwiebel", D("1"), "", "kleine Zwiebel", ""),
	("3 Eier", D("3"), "", "Eier", ""),
	("2 Tomaten", D("2"), "", "Tomaten", ""),
	("1 cup flour, sifted", D("1"), "Tasse", "flour", "sifted"),
	("1 cup of flour", D("1"), "Tasse", "flour", ""),
	("2 tbsp olive oil", D("2"), "EL", "olive oil", ""),
	("1/4 tsp salt", D("0.25"), "TL", "salt", ""),
	("2 T sugar", D("2"), "EL", "sugar", ""),
	("2 t salt", D("2"), "TL", "salt", ""),
	("1 (14 oz) can chickpeas", D("1"), "Dose", "chickpeas", "14 oz"),
	("1 Dose Kokosmilch (400 ml)", D("1"), "Dose", "Kokosmilch", "400 ml"),
	("Zucker nach Belieben", None, "", "Zucker", "nach Belieben"),
	("Olivenöl zum Servieren", None, "", "Olivenöl", "zum Servieren"),
	("Chili flakes, to taste", None, "", "Chili flakes", "to taste"),
	("Chili flakes to taste", None, "", "Chili flakes", "to taste"),
	("Koriander (optional)", None, "", "Koriander", "optional"),
	("Koriander optional", None, "", "Koriander", "optional"),
	("1 Pck. Vanillezucker", D("1"), "Pck", "Vanillezucker", ""),
	("1 Päckchen Backpulver", D("1"), "Pck", "Backpulver", ""),
	("100ml Milch", D("100"), "ml", "Milch", ""),
	("1kg Kartoffeln", D("1"), "kg", "Kartoffeln", ""),
	("2 EL Butter zum Anbraten", D("2"), "EL", "Butter", "zum Anbraten"),
	("4 Scheiben Brot", D("4"), "Scheibe", "Brot", ""),
	("1.5 kg Rindfleisch", D("1.5"), "kg", "Rindfleisch", ""),
	("0,5 l Milch", D("0.5"), "l", "Milch", ""),
	("500 gr Hackfleisch", D("500"), "g", "Hackfleisch", ""),
	("3 Esslöffel Zucker", D("3"), "EL", "Zucker", ""),
	("2 Teelöffel Backpulver", D("2"), "TL", "Backpulver", ""),
	("1 Msp. Zimt", D("1"), "Msp", "Zimt", ""),
	("2 Blätter Lorbeer", D("2"), "Blatt", "Lorbeer", ""),
	("1 lb ground beef", D("1"), "lb", "ground beef", ""),
	("8 oz cream cheese", D("8"), "oz", "cream cheese", ""),
	("1 Becher Sauerrahm", D("1"), "Becher", "Sauerrahm", ""),
	("1 Glas Weisswein", D("1"), "Glas", "Weisswein", ""),
	("1 Stk. Zitrone", D("1"), "Stück", "Zitrone", ""),
	("3 Stück Hähnchenbrust", D("3"), "Stück", "Hähnchenbrust", ""),
	("- 2 Eier", D("2"), "", "Eier", ""),
	("• 2 Eier", D("2"), "", "Eier", ""),
	("1 Bund Rucola, gewaschen (ca. 100 g)", D("1"), "Bund", "Rucola",
	 "gewaschen (ca. 100 g)"),
	("2 Zehen Knoblauch (gepresst), fein gehackt", D("2"), "Zehe",
	 "Knoblauch", "gepresst; fein gehackt"),
	("Mehl für die Form", None, "", "Mehl", "für die Form"),
	("Salz, Pfeffer", None, "", "Salz", "Pfeffer"),
	("Butter.", None, "", "Butter", ""),
	("250 g", D("250"), "g", "250 g", ""),
	("1/0 TL Salz", None, "", "1/0 TL Salz", ""),
	("99999999 g Mehl", None, "", "99999999 g Mehl", ""),
])
def test_parse_line(raw, amount, unit, name, note):
	got = parse_line(raw)
	assert (got.amount, got.unit, got.name, got.note) == (
		amount, unit, name, note)


def test_raw_is_kept_stripped():
	got = parse_line("  250 g Mehl  ")
	assert got.raw == "250 g Mehl"
	assert parse_line("ca. 200 g Feta").raw == "ca. 200 g Feta"


def test_parse_lines_skips_blank_lines():
	got = parse_lines(["", "  ", "250 g Mehl", "\t", "Salz"])
	assert [g.name for g in got] == ["Mehl", "Salz"]


def test_empty_line_raises():
	with pytest.raises(ValueError):
		parse_line("   ")


@pytest.mark.parametrize("raw", ["0,12345 g Salz", "⅔ cup milk", "1/3 l"])
def test_amount_has_at_most_three_decimals(raw):
	amount = parse_line(raw).amount
	assert amount is not None
	assert amount.as_tuple().exponent >= -3


def test_long_line_is_truncated_not_rejected():
	name = "a" * (NAME_LEN + 100)
	got = parse_line("1 kg " + name + ", " + "b" * (NAME_LEN + 100))
	assert len(got.name) == NAME_LEN
	assert len(got.note) == NAME_LEN
	assert got.raw.endswith("b")
	assert len(got.unit) <= UNIT_LEN


def test_canonical_units_fit_schema():
	assert all(len(unit) <= UNIT_LEN for unit in UNITS)
	assert all(unit.strip() == unit for unit in UNITS)


@pytest.mark.parametrize("raw", ["Salz", "250 g", "1 Tasse", "- ,"])
def test_name_never_empty(raw):
	assert parse_line(raw).name
