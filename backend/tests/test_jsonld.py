"""schema.org/Recipe extraction from JSON-LD fixtures."""

import json
from pathlib import Path

from app.importer import jsonld

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
	return jsonld.extract((FIXTURES / name).read_text(encoding="utf-8"))


def html_with(node: dict) -> str:
	return ('<html><head><script type="application/ld+json">'
		+ json.dumps(node) + "</script></head><body></body></html>")


def recipe(**fields) -> str:
	node = {"@context": "https://schema.org", "@type": "Recipe",
		"name": "Test"}
	node.update(fields)
	return html_with(node)


def test_simple_title_intro_and_image():
	data = load("jsonld_simple.html")
	assert data.title == "Kartoffelsuppe"
	assert data.intro == "Eine cremige Suppe für kalte Tage."
	assert data.image_url == "https://example.org/img/suppe.jpg"


def test_simple_lists_and_yield():
	data = load("jsonld_simple.html")
	assert len(data.ingredient_lines) == 5
	assert data.ingredient_lines[0] == "800 g Kartoffeln"
	assert len(data.steps) == 4
	assert data.steps[-1] == "Pürieren, Sahne einrühren, abschmecken."
	assert data.servings == 4


def test_simple_iso_times():
	data = load("jsonld_simple.html")
	assert data.prep_minutes == 20
	assert data.cook_minutes == 70
	assert data.warnings == []


def test_graph_with_type_list():
	data = load("jsonld_graph.html")
	assert data is not None
	assert data.title == "Lasagne al forno"


def test_graph_description_without_tags_or_entities():
	data = load("jsonld_graph.html")
	assert data.intro == ("Ein Klassiker & schnell gemacht. "
			      "Mit viel Käse überbacken.")
	assert "<" not in data.intro and "&amp;" not in data.intro


def test_graph_sections_flattened():
	data = load("jsonld_graph.html")
	assert len(data.steps) == 5
	assert data.steps[0] == "Zwiebel und Knoblauch würfeln und anbraten."
	assert data.steps[1] == ("Hackfleisch zugeben, kräftig anbraten, "
				 "Tomaten dazu.")
	assert data.steps[-1] == "Bei 180 °C 35 Minuten backen."


def test_graph_ingredients_entities_unescaped():
	data = load("jsonld_graph.html")
	assert len(data.ingredient_lines) == 6
	assert data.ingredient_lines[4] == "1 ½ TL Salz"


def test_graph_image_object_list_and_yield_list():
	data = load("jsonld_graph.html")
	assert data.image_url == "https://example.org/img/lasagne-1.jpg"
	assert data.servings == 6


def test_graph_total_time_only_becomes_cook_time_with_warning():
	data = load("jsonld_graph.html")
	assert data.prep_minutes is None
	assert data.cook_minutes == 45
	assert any("Gesamtzeit" in w for w in data.warnings)


def test_broken_first_block_is_skipped():
	data = load("jsonld_broken.html")
	assert data is not None
	assert data.title == "Pfannkuchen"


def test_broken_main_entity_and_comment_wrapper():
	data = load("jsonld_broken.html")
	assert data.servings == 2
	assert data.prep_minutes == 15
	assert data.cook_minutes is None
	assert data.image_url == "https://example.org/img/pfannkuchen.jpg"


def test_broken_string_ingredients_and_numbered_instructions():
	data = load("jsonld_broken.html")
	assert data.ingredient_lines == ["200 g Mehl", "2 Eier",
					 "300 ml Milch", "1 Prise Salz"]
	assert len(data.steps) == 3
	assert data.steps[1] == "Teig 10 Minuten ruhen lassen."


def test_none_without_recipe_node():
	assert load("jsonld_none.html") is None


def test_none_without_ld_json():
	assert jsonld.extract("<html><body><h1>Hi</h1></body></html>") is None


def test_yield_variants():
	for value, expected in [(4, 4), ("4", 4), ("Serves 4", 4),
				("4 Portionen", 4), (["8", "8 Stück"], 8),
				("viele", None), (0, None)]:
		data = jsonld.extract(recipe(recipeYield=value))
		assert data.servings == expected, value


def test_instructions_string_split_on_newlines():
	data = jsonld.extract(recipe(
		recipeInstructions="Teig kneten.\nRuhen lassen.\n\nBacken."))
	assert data.steps == ["Teig kneten.", "Ruhen lassen.", "Backen."]


def test_instructions_html_string_split_on_breaks():
	data = jsonld.extract(recipe(
		recipeInstructions="<p>Teig kneten.</p><p>Backen &amp; "
				   "geniessen.</p>"))
	assert data.steps == ["Teig kneten.", "Backen & geniessen."]


def test_instructions_howtostep_name_only_and_nested_lists():
	data = jsonld.extract(recipe(recipeInstructions=[
		[{"@type": "HowToStep", "name": "Erster"}],
		[["Zweiter", {"@type": "HowToStep", "text": "Dritter"}]],
	]))
	assert data.steps == ["Erster", "Zweiter", "Dritter"]


def test_image_variants():
	cases = [
		("https://e.org/a.jpg", "https://e.org/a.jpg"),
		(["https://e.org/b.jpg", "https://e.org/c.jpg"],
		 "https://e.org/b.jpg"),
		({"@type": "ImageObject", "url": "https://e.org/d.jpg"},
		 "https://e.org/d.jpg"),
		({"@type": "ImageObject", "contentUrl": "https://e.org/e.jpg"},
		 "https://e.org/e.jpg"),
		([{"@type": "ImageObject", "url": "https://e.org/f.jpg"}],
		 "https://e.org/f.jpg"),
		([], None),
	]
	for value, expected in cases:
		assert jsonld.extract(recipe(image=value)).image_url == expected


def test_recipe_without_ingredients_and_steps_returns_with_warning():
	data = jsonld.extract(recipe(description="Nur Text"))
	assert data is not None
	assert data.title == "Test"
	assert data.ingredient_lines == [] and data.steps == []
	assert any("ohne Zutaten" in w for w in data.warnings)


def test_recipe_type_in_mixed_list_and_type_case():
	data = jsonld.extract(html_with([
		{"@type": "WebSite", "name": "Site"},
		{"@type": "http://schema.org/Recipe", "name": "Aus Liste",
		 "recipeIngredient": ["1 Ei"]},
	]))
	assert data.title == "Aus Liste"
	assert data.ingredient_lines == ["1 Ei"]


def test_single_string_ingredient_and_tags_stripped():
	data = jsonld.extract(recipe(
		recipeIngredient="<b>2</b> Eier &amp; 1 Prise  Salz"))
	assert data.ingredient_lines == ["2 Eier & 1 Prise Salz"]
