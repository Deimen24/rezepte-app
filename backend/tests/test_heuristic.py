"""Heuristic recipe extraction from plain HTML fixtures."""

from pathlib import Path

from app.importer import heuristic

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
	return heuristic.extract((FIXTURES / name).read_text(encoding="utf-8"))


def page(head: str = "", body: str = "") -> str:
	return f"<html><head>{head}</head><body>{body}</body></html>"


def test_de_title_from_og_title():
	data = load("heuristic_de.html")
	assert data.title == "Käsespätzle – Omas Rezept"


def test_de_intro_and_image_from_meta():
	data = load("heuristic_de.html")
	assert data.intro == ("Deftige Käsespätzle mit Röstzwiebeln, "
			      "wie bei Oma.")
	assert data.image_url == "https://example.org/img/spaetzle.jpg"


def test_de_servings_and_times():
	data = load("heuristic_de.html")
	assert data.servings == 4
	assert data.prep_minutes == 30
	assert data.cook_minutes == 20


def test_de_ingredients_after_heading_skip_empty_items():
	data = load("heuristic_de.html")
	assert len(data.ingredient_lines) == 6
	assert data.ingredient_lines[0] == "400 g Mehl"
	assert data.ingredient_lines[-1] == "2 Zwiebeln"


def test_de_steps_from_ol_after_heading_not_longest_ol():
	data = load("heuristic_de.html")
	assert len(data.steps) == 4
	assert data.steps[0].startswith("Mehl, Eier, Wasser")


def test_de_has_no_warnings():
	assert load("heuristic_de.html").warnings == []


def test_en_title_from_h1_without_og_title():
	assert load("heuristic_en.html").title == "Banana Bread"


def test_en_intro_from_name_description():
	assert load("heuristic_en.html").intro == \
		"Moist banana bread with walnuts."


def test_en_servings_and_times_with_hours():
	data = load("heuristic_en.html")
	assert data.servings == 8
	assert data.prep_minutes == 15
	assert data.cook_minutes == 65


def test_en_ingredients_after_heading():
	data = load("heuristic_en.html")
	assert len(data.ingredient_lines) == 5
	assert data.ingredient_lines[1] == "1/3 cup melted butter"


def test_en_steps_from_paragraphs_until_next_heading():
	data = load("heuristic_en.html")
	assert len(data.steps) == 3
	assert data.steps[0].startswith("Preheat the oven")
	assert data.steps[-1].startswith("Bake for about")
	assert data.warnings == []
	assert data.image_url is None


def test_bare_title_from_title_tag_without_site_suffix():
	assert load("heuristic_bare.html").title == "Pfannkuchen"


def test_bare_ingredients_guessed_by_quantities_ignoring_nav():
	data = load("heuristic_bare.html")
	assert len(data.ingredient_lines) == 5
	assert data.ingredient_lines[3] == "½ TL Salz"
	assert "Zutaten geraten" in data.warnings


def test_bare_steps_from_longest_ol():
	data = load("heuristic_bare.html")
	assert len(data.steps) == 4
	assert data.steps[0].startswith("Mehl, Eier und Milch")
	assert "Schritte geraten" in data.warnings


def test_bare_no_meta_fields():
	data = load("heuristic_bare.html")
	assert data.intro == ""
	assert data.image_url is None
	assert data.servings is None
	assert data.prep_minutes is None


def test_empty_page_warnings():
	data = heuristic.extract(page(body="<p>Nichts</p>"))
	assert data.title == ""
	assert data.ingredient_lines == [] and data.steps == []
	assert "Zutaten nicht gefunden" in data.warnings
	assert "Schritte nicht gefunden" in data.warnings
	assert "Titel nicht gefunden" in data.warnings


def test_title_suffix_kept_when_remainder_empty():
	data = heuristic.extract(page(head="<title> - Foo</title>"))
	assert data.title == "- Foo"
	data = heuristic.extract(page(head="<title>A | B - C</title>"))
	assert data.title == "A"


def test_strong_label_counts_as_heading():
	body = ("<p><strong>Zutaten:</strong></p><ul><li>1 Ei</li>"
		"<li>Salz</li></ul><p><b>So geht's</b></p>"
		"<ol><li>Rühren.</li></ol>")
	data = heuristic.extract(page(body=body))
	assert data.ingredient_lines == ["1 Ei", "Salz"]
	assert data.steps == ["Rühren."]
	assert data.warnings == ["Titel nicht gefunden"]


def test_long_and_empty_ingredient_items_ignored():
	body = ("<h2>Zutaten</h2><ul><li>1 Ei</li><li>   </li><li>"
		+ "x" * 301 + "</li></ul>")
	data = heuristic.extract(page(body=body))
	assert data.ingredient_lines == ["1 Ei"]


def test_guess_needs_three_quantity_items():
	body = "<ul><li>1 Ei</li><li>2 Eier</li><li>Salz</li></ul>"
	data = heuristic.extract(page(body=body))
	assert data.ingredient_lines == []
	assert "Zutaten nicht gefunden" in data.warnings


def test_texts_without_tags_or_entities():
	body = ("<h2>Zutaten</h2><ul><li><b>1</b> Ei &amp; Salz</li>"
		"<li>2 &frac12; EL\n  Öl</li><li>3 x</li></ul>"
		"<h2>Zubereitung</h2><ol><li>R&uuml;hren<br>und backen.</li>"
		"</ol>")
	data = heuristic.extract(page(body=body))
	assert data.ingredient_lines[:2] == ["1 Ei & Salz", "2 ½ EL Öl"]
	assert data.steps == ["Rühren und backen."]


def test_heading_label_preferred_over_short_paragraph():
	body = ("<p>Zubereitung: 30 Min</p><h2>Zutaten</h2><ul><li>1 Ei</li>"
		"</ul><h2>Zubereitung</h2><ol><li>Rühren.</li></ol>")
	data = heuristic.extract(page(body=body))
	assert data.steps == ["Rühren."]
	assert data.prep_minutes == 30
	assert "Schritte geraten" not in data.warnings
