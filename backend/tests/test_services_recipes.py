"""Recipe service layer, called directly with a database session."""

from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.models import (
	Category,
	Ingredient,
	RecipeTag,
	RecipeVersion,
	Step,
	Tag,
)
from app.schemas import RecipeInput
from app.services import recipes as service
from app.services import taxonomy


def recipe_input(title="Kürbissuppe", tags=("vegi", "Herbst"),
		 ingredients=None, steps=None, category_id=None,
		 intro="Cremig."):
	if ingredients is None:
		ingredients = [
			{"amount": "250", "unit": "g", "name": "Kürbis"},
			{"amount": "0.5", "unit": "TL", "name": "Salz"},
			{"amount": None, "unit": "", "name": "Pfeffer"},
		]
	if steps is None:
		steps = [{"text": "Würfeln."}, {"text": "Kochen."}]
	return RecipeInput(
		category_id=category_id,
		tags=list(tags),
		favorite=False,
		source={"kind": "none"},
		version={
			"title": title,
			"intro": intro,
			"servings": 4,
			"ingredients": ingredients,
			"steps": steps,
		},
	)


def count(db, model) -> int:
	return db.scalar(select(func.count()).select_from(model))


def snapshot(version: RecipeVersion) -> dict:
	"""Content of a version without ids, for equality checks."""
	return {
		"title": version.title,
		"intro": version.intro,
		"servings": version.servings,
		"ingredients": [(i.position, i.amount, i.unit, i.name, i.note)
				for i in version.ingredients],
		"steps": [(s.position, s.text) for s in version.steps],
	}


def test_create_yields_two_distinct_versions_with_equal_content(db):
	recipe = service.create_recipe(db, recipe_input())
	kinds = sorted(v.kind.value for v in recipe.versions)
	assert kinds == ["original", "own"]
	assert recipe.original.id != recipe.own.id
	assert snapshot(recipe.original) == snapshot(recipe.own)
	assert recipe.original.ingredients[0].amount == Decimal("250")
	assert recipe.original.ingredients[2].amount is None


def test_create_writes_separate_ingredient_rows_per_version(db):
	recipe = service.create_recipe(db, recipe_input())
	own_ids = {i.id for i in recipe.own.ingredients}
	orig_ids = {i.id for i in recipe.original.ingredients}
	assert own_ids.isdisjoint(orig_ids)
	assert count(db, Ingredient) == 6
	assert count(db, Step) == 4


def test_update_leaves_original_rows_untouched(db):
	recipe = service.create_recipe(db, recipe_input())
	orig_id = recipe.original.id
	before_ing = [(i.id, i.name, i.amount)
		      for i in recipe.original.ingredients]
	before_steps = [(s.id, s.text) for s in recipe.original.steps]

	changed = recipe_input(title="Scharf", ingredients=[
		{"amount": "300", "unit": "g", "name": "Kürbis"},
		{"amount": "1", "unit": "", "name": "Chili"},
	], steps=[{"text": "Mit Chili kochen."}])
	updated = service.update_recipe(db, recipe.id, changed)

	assert updated.original.id == orig_id
	assert updated.original.title == "Kürbissuppe"
	after_ing = [(i.id, i.name, i.amount)
		     for i in updated.original.ingredients]
	after_steps = [(s.id, s.text) for s in updated.original.steps]
	assert after_ing == before_ing
	assert after_steps == before_steps
	assert updated.own.title == "Scharf"


def test_update_renumbers_positions_and_drops_removed_rows(db):
	recipe = service.create_recipe(db, recipe_input())
	changed = recipe_input(ingredients=[
		{"amount": "1", "unit": "", "name": "Chili"},
		{"amount": "2", "unit": "", "name": "Knoblauch"},
	], steps=[{"text": "Nur ein Schritt."}])
	updated = service.update_recipe(db, recipe.id, changed)

	assert [i.position for i in updated.own.ingredients] == [0, 1]
	assert [s.position for s in updated.own.steps] == [0]
	# original: 3 ingredients + 2 steps; own: 2 + 1; no orphans
	assert count(db, Ingredient) == 5
	assert count(db, Step) == 3
	own_rows = db.scalars(select(Ingredient.name).where(
		Ingredient.version_id == updated.own.id)).all()
	assert sorted(own_rows) == ["Chili", "Knoblauch"]


def test_update_unknown_recipe_returns_none(db):
	assert service.update_recipe(db, 9999, recipe_input()) is None


def test_update_unknown_category_raises_and_keeps_recipe(db):
	recipe = service.create_recipe(db, recipe_input())
	with pytest.raises(ValueError):
		service.update_recipe(db, recipe.id,
				      recipe_input(category_id=12345))
	db.rollback()
	again = service.get_recipe(db, recipe.id)
	assert again.category_id is None
	assert again.own.title == "Kürbissuppe"


def test_delete_cascades_to_all_child_rows(db):
	recipe = service.create_recipe(db, recipe_input())
	assert count(db, RecipeVersion) == 2
	assert count(db, RecipeTag) == 2
	assert service.delete_recipe(db, recipe.id) is True
	assert count(db, RecipeVersion) == 0
	assert count(db, Ingredient) == 0
	assert count(db, Step) == 0
	assert count(db, RecipeTag) == 0
	assert service.get_recipe(db, recipe.id) is None


def test_delete_keeps_tags_and_category(db):
	cat = taxonomy.create_category(db, "Suppen")
	recipe = service.create_recipe(db, recipe_input(category_id=cat.id))
	service.delete_recipe(db, recipe.id)
	assert count(db, Tag) == 2
	assert count(db, Category) == 1


def test_delete_unknown_recipe_returns_false(db):
	assert service.delete_recipe(db, 9999) is False


def test_tags_are_reused_across_recipes(db):
	first = service.create_recipe(db, recipe_input(tags=["vegi"]))
	second = service.create_recipe(db, recipe_input(title="Risotto",
							tags=["Vegi"]))
	assert [t.id for t in first.tags] == [t.id for t in second.tags]
	assert count(db, Tag) == 1
	assert db.scalar(select(Tag)).name == "vegi"


def test_removing_tag_from_recipe_keeps_tag_row(db):
	recipe = service.create_recipe(db, recipe_input(tags=["vegi",
							     "herbst"]))
	updated = service.update_recipe(db, recipe.id,
					recipe_input(tags=["vegi"]))
	assert [t.name for t in updated.tags] == ["vegi"]
	assert count(db, RecipeTag) == 1
	assert sorted(db.scalars(select(Tag.name))) == ["herbst", "vegi"]


def test_deleting_category_sets_recipe_category_null(db):
	cat = taxonomy.create_category(db, "Suppen")
	recipe = service.create_recipe(db, recipe_input(category_id=cat.id))
	assert recipe.category_id == cat.id
	# Plain SQL delete: only the ON DELETE SET NULL rule can null it.
	db.execute(delete(Category).where(Category.id == cat.id))
	db.commit()
	reloaded = service.get_recipe(db, recipe.id)
	assert reloaded.category_id is None
	assert reloaded.category is None


def test_list_with_empty_filters_returns_all(db):
	service.create_recipe(db, recipe_input(title="Suppe"))
	service.create_recipe(db, recipe_input(title="Brot"))
	items = service.list_recipes(db, q="", tags=[], ingredients=[])
	assert [i["title"] for i in items] == ["Brot", "Suppe"]
	assert set(items[0]) == {"id", "title", "category", "tags",
				 "favorite", "updated_at"}


def test_list_q_without_match_returns_empty_list(db):
	service.create_recipe(db, recipe_input())
	assert service.list_recipes(db, q="Ananas") == []
	assert service.list_recipes(db, ingredients=["Ananas"]) == []
	assert service.list_recipes(db, tags=["nix"]) == []


def test_list_on_empty_database_returns_empty_list(db):
	assert service.list_recipes(db) == []
