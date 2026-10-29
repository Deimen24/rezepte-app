"""Pydantic input validation edge cases and amount rendering."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import NAME_LEN, UNIT_LEN
from app.schemas import (
	IngredientIn,
	RecipeInput,
	Source,
	StepIn,
	VersionIn,
	amount_to_str,
)


def version(**extra) -> dict:
	data = {"title": "Suppe"}
	data.update(extra)
	return data


@pytest.mark.parametrize("bad", ["1/2", "1,5", "abc", "", "1 kg"])
def test_amount_rejects_non_decimal_text(bad):
	with pytest.raises(ValidationError):
		IngredientIn(amount=bad, name="Mehl")


@pytest.mark.parametrize("raw, expected", [
	("0.5", Decimal("0.5")),
	("250", Decimal("250")),
	(0.5, Decimal("0.5")),
	(2, Decimal("2")),
	(None, None),
])
def test_amount_accepts_decimal_text_number_and_null(raw, expected):
	assert IngredientIn(amount=raw, name="Mehl").amount == expected


def test_ingredient_name_required_and_stripped():
	assert IngredientIn(name="  Mehl ").name == "Mehl"
	with pytest.raises(ValidationError):
		IngredientIn(name="   ")
	with pytest.raises(ValidationError):
		IngredientIn()


def test_ingredient_null_unit_and_note_become_empty_strings():
	ing = IngredientIn(name="Mehl", unit=None, note=None)
	assert ing.unit == ""
	assert ing.note == ""


def test_ingredient_unit_too_long_rejected():
	with pytest.raises(ValidationError):
		IngredientIn(name="Mehl", unit="x" * (UNIT_LEN + 1))


@pytest.mark.parametrize("field", ["servings", "prep_minutes",
				   "cook_minutes"])
def test_negative_counts_rejected_zero_allowed(field):
	with pytest.raises(ValidationError):
		VersionIn(**version(**{field: -1}))
	assert getattr(VersionIn(**version(**{field: 0})), field) == 0
	assert getattr(VersionIn(**version()), field) is None


def test_title_whitespace_only_rejected():
	with pytest.raises(ValidationError):
		VersionIn(**version(title="   \t "))


def test_title_too_long_rejected_at_limit_accepted():
	with pytest.raises(ValidationError):
		VersionIn(**version(title="x" * (NAME_LEN + 1)))
	assert len(VersionIn(**version(title="x" * NAME_LEN)).title) \
		== NAME_LEN


def test_title_and_intro_stripped_and_null_intro_allowed():
	v = VersionIn(**version(title=" Suppe ", intro=None))
	assert v.title == "Suppe"
	assert v.intro == ""


def test_step_text_stripped_and_empty_rejected():
	assert StepIn(text="  Kochen. ").text == "Kochen."
	with pytest.raises(ValidationError):
		StepIn(text="  ")


def test_tags_deduplicated_ignoring_case_and_stripped():
	data = RecipeInput(version=version(),
			   tags=[" Vegi ", "vegi", "", "  ", "Herbst",
				 "HERBST", "schnell"])
	assert data.tags == ["Vegi", "Herbst", "schnell"]


def test_tags_default_empty_and_first_spelling_wins():
	assert RecipeInput(version=version()).tags == []
	data = RecipeInput(version=version(), tags=["vegi", "Vegi"])
	assert data.tags == ["vegi"]


def test_source_kind_url_without_url_rejected():
	with pytest.raises(ValidationError):
		Source(kind="url")
	with pytest.raises(ValidationError):
		Source(kind="url", url="   ")


def test_source_kind_book_without_book_rejected():
	with pytest.raises(ValidationError):
		Source(kind="book", page="12")
	src = Source(kind="book", book=" Tiptopf ", page=" 12 ")
	assert (src.book, src.page) == ("Tiptopf", "12")


def test_source_kind_none_with_url_is_tolerated():
	# Implemented behaviour: check_kind() only demands the field that
	# the kind needs; extra fields are kept as given, not rejected
	# and not cleared. The frontend decides what to show per kind.
	src = Source(kind="none", url="https://example.org")
	assert src.kind == "none"
	assert src.url == "https://example.org"


def test_source_unknown_kind_rejected():
	with pytest.raises(ValidationError):
		Source(kind="tv")


def test_source_empty_strings_become_null():
	src = Source(kind="none", url="", book="  ", page="")
	assert (src.url, src.book, src.page) == (None, None, None)


def test_source_defaults_to_kind_none():
	data = RecipeInput(version=version())
	assert data.source.model_dump() == {"kind": "none", "url": None,
					    "book": None, "page": None}


@pytest.mark.parametrize("value, expected", [
	(None, None),
	(Decimal("0.500"), "0.5"),
	(Decimal("2.000"), "2"),
	(Decimal("250"), "250"),
	(Decimal("1.25"), "1.25"),
	(Decimal("0"), "0"),
	(Decimal("0.000"), "0"),
	(Decimal("100.100"), "100.1"),
	(Decimal("1E+3"), "1000"),
	(Decimal("0.001"), "0.001"),
])
def test_amount_to_str_drops_trailing_zeros(value, expected):
	assert amount_to_str(value) == expected
