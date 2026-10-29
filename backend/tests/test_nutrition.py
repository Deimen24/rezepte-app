"""Nutrition per portion: API round trip, export and JSON-LD import."""

import copy
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.importer import jsonld
from app.models import Recipe, RecipeVersion
from app.services import importer as service
from tests.test_jsonld import recipe as jsonld_page
from tests.test_recipes import RECIPE, post_recipe

FIXTURE = Path(__file__).parent / "fixtures" / "jsonld_nutrition.html"
NUTRITION = {"kcal": "250", "protein_g": "12.5", "carbs_g": "30",
	     "fat_g": 8.2}
NULLS = {"kcal": None, "protein_g": None, "carbs_g": None, "fat_g": None}
COLUMNS = ("kcal", "protein_g", "carbs_g", "fat_g")


def with_nutrition(values=NUTRITION) -> dict:
	data = copy.deepcopy(RECIPE)
	data["version"]["nutrition"] = values
	return data


def serve(monkeypatch, html: str):
	monkeypatch.setattr(service, "fetch_html",
			    lambda url, client=None: (html, url))


def fetch_preview(client, monkeypatch, html: str) -> dict:
	serve(monkeypatch, html)
	resp = client.post("/api/import/fetch",
			   json={"url": "https://example.com/x"})
	assert resp.status_code == 200, resp.text
	return resp.json()


def test_create_and_get_nutrition_strings(auth_client):
	body = post_recipe(auth_client, with_nutrition())
	assert body["own"]["nutrition"] == {
		"kcal": "250", "protein_g": "12.5", "carbs_g": "30",
		"fat_g": "8.2"}
	assert body["original"]["nutrition"] == body["own"]["nutrition"]
	resp = auth_client.get(f"/api/recipes/{body['id']}")
	assert resp.json()["own"]["nutrition"]["kcal"] == "250"


def test_omitted_nutrition_is_null(auth_client):
	body = post_recipe(auth_client)
	assert body["own"]["nutrition"] == NULLS
	assert body["original"]["nutrition"] == NULLS


def test_partial_nutrition(auth_client):
	body = post_recipe(auth_client, with_nutrition({"kcal": 180}))
	assert body["own"]["nutrition"] == dict(NULLS, kcal="180")


@pytest.mark.parametrize("field", COLUMNS)
@pytest.mark.parametrize("value", ["-1", "100000", "abc"])
def test_invalid_nutrition_rejected(auth_client, field, value):
	data = with_nutrition({field: value})
	resp = auth_client.post("/api/recipes", json=data)
	assert resp.status_code == 422


def test_update_changes_own_only(auth_client):
	body = post_recipe(auth_client, with_nutrition())
	data = with_nutrition({"kcal": "300", "fat_g": None})
	resp = auth_client.put(f"/api/recipes/{body['id']}", json=data)
	assert resp.status_code == 200, resp.text
	updated = resp.json()
	assert updated["own"]["nutrition"] == dict(NULLS, kcal="300")
	assert updated["original"]["nutrition"] == body["original"][
		"nutrition"]


def test_export_contains_nutrition(auth_client):
	body = post_recipe(auth_client, with_nutrition())
	resp = auth_client.get("/api/export")
	assert resp.status_code == 200, resp.text
	zf = zipfile.ZipFile(io.BytesIO(resp.content))
	data = json.loads(zf.read("recipes.json"))
	exported = next(r for r in data["recipes"] if r["id"] == body["id"])
	assert exported["own"]["nutrition"]["kcal"] == "250"
	assert exported["own"]["nutrition"]["protein_g"] == "12.5"


def test_columns_exist_and_store_decimals(db):
	cols = {c["name"] for c in inspect(db.bind).get_columns(
		"recipe_versions")}
	assert set(COLUMNS) <= cols
	version = RecipeVersion(kind="own", title="T", kcal=Decimal("1.5"))
	recipe = Recipe(versions=[version])
	db.add(recipe)
	db.flush()
	db.refresh(version)
	assert version.kcal == Decimal("1.5")
	assert version.fat_g is None


def test_jsonld_fixture_nutrition():
	data = jsonld.extract(FIXTURE.read_text(encoding="utf-8"))
	assert data.kcal == Decimal("250.0")
	assert data.protein_g == Decimal("12.5")
	assert data.carbs_g == Decimal("30.0")
	assert data.fat_g == Decimal("8.3")


@pytest.mark.parametrize("raw, expected", [
	("250 kcal", "250.0"), ("250 calories", "250.0"), ("250", "250.0"),
	(250, "250.0"), (12.5, "12.5"), ("12.5 g", "12.5"),
	("12,5 g", "12.5"), (" 7 G ", "7.0"),
])
def test_nutrient_values(raw, expected):
	assert jsonld._nutrient(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [
	"viel", "", None, "1.2.3", "-5 g", "100000 kcal", "250 kcal pro",
	True, [], {}, "12 mg",
])
def test_nutrient_garbage_is_none(raw):
	assert jsonld._nutrient(raw) is None


def test_jsonld_without_nutrition():
	data = jsonld.extract(jsonld_page(recipeIngredient=["1 Ei"]))
	assert (data.kcal, data.protein_g, data.carbs_g, data.fat_g) == (
		None, None, None, None)


def test_preview_fills_nutrition(auth_client, monkeypatch):
	body = fetch_preview(auth_client, monkeypatch,
			     FIXTURE.read_text(encoding="utf-8"))
	assert body["method"] == "jsonld"
	assert body["version"]["nutrition"] == {
		"kcal": "250", "protein_g": "12.5", "carbs_g": "30",
		"fat_g": "8.3"}


def test_preview_garbage_nutrition_is_null(auth_client, monkeypatch):
	html = jsonld_page(
		recipeIngredient=["1 Ei"], recipeInstructions=["Kochen."],
		nutrition={"@type": "NutritionInformation",
			   "calories": "viel", "proteinContent": "k.A.",
			   "carbohydrateContent": "", "fatContent": None})
	body = fetch_preview(auth_client, monkeypatch, html)
	assert body["version"]["nutrition"] == NULLS


def test_preview_round_trip_saves_nutrition(auth_client, monkeypatch):
	body = fetch_preview(auth_client, monkeypatch,
			     FIXTURE.read_text(encoding="utf-8"))
	version = body["version"]
	for item in version["ingredients"]:
		item.pop("raw")
	saved = post_recipe(auth_client, {
		"category_id": None, "tags": [], "favorite": False,
		"source": body["source"], "version": version})
	assert saved["own"]["nutrition"]["kcal"] == "250"
