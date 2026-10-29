"""Recipe business logic: create, read, update, delete and filtered list."""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app import storage
from app.models import (
	Category,
	CookLog,
	Ingredient,
	Note,
	Photo,
	Recipe,
	RecipeTag,
	RecipeVersion,
	SourceKind,
	Step,
	Tag,
	VersionKind,
)
from app.schemas import RecipeInput, VersionIn
from app.services import photos
from app.services.taxonomy import get_or_create_tags

LOAD_ALL = (
	selectinload(Recipe.category),
	selectinload(Recipe.tags),
	selectinload(Recipe.versions).selectinload(RecipeVersion.ingredients),
	selectinload(Recipe.versions).selectinload(RecipeVersion.steps),
	selectinload(Recipe.notes),
	selectinload(Recipe.cook_log),
	selectinload(Recipe.photos),
)


def set_version(version: RecipeVersion, data: VersionIn) -> None:
	"""Overwrite all editable fields of a version from the input."""
	version.title = data.title
	version.intro = data.intro
	version.servings = data.servings
	version.prep_minutes = data.prep_minutes
	version.cook_minutes = data.cook_minutes
	version.ingredients = [
		Ingredient(position=i, amount=ing.amount, unit=ing.unit,
			   name=ing.name, note=ing.note)
		for i, ing in enumerate(data.ingredients)
	]
	version.steps = [
		Step(position=i, text=step.text)
		for i, step in enumerate(data.steps)
	]


def check_category(db: Session, category_id: int | None) -> None:
	if category_id is None:
		return
	if db.get(Category, category_id) is None:
		raise ValueError("category not found")


def set_meta(db: Session, recipe: Recipe, data: RecipeInput) -> None:
	"""Apply category, tags, favorite and source to the recipe row."""
	check_category(db, data.category_id)
	recipe.category_id = data.category_id
	recipe.favorite = data.favorite
	recipe.source_kind = SourceKind(data.source.kind)
	recipe.source_url = data.source.url
	recipe.source_book = data.source.book
	recipe.source_page = data.source.page
	recipe.tags = get_or_create_tags(db, data.tags)


def create_recipe(db: Session, data: RecipeInput) -> Recipe:
	recipe = Recipe()
	set_meta(db, recipe, data)
	for kind in (VersionKind.ORIGINAL, VersionKind.OWN):
		version = RecipeVersion(kind=kind)
		set_version(version, data.version)
		recipe.versions.append(version)
	db.add(recipe)
	db.commit()
	return get_recipe(db, recipe.id)


def get_recipe(db: Session, recipe_id: int) -> Recipe | None:
	stmt = (
		select(Recipe)
		.where(Recipe.id == recipe_id)
		.options(*LOAD_ALL)
		.execution_options(populate_existing=True)
	)
	return db.scalars(stmt).first()


def update_recipe(db: Session, recipe_id: int,
		  data: RecipeInput) -> Recipe | None:
	"""Replace metadata and the own version; original is never touched."""
	recipe = get_recipe(db, recipe_id)
	if recipe is None:
		return None
	set_meta(db, recipe, data)
	set_version(recipe.own, data.version)
	recipe.updated_at = func.now()
	db.commit()
	return get_recipe(db, recipe_id)


def delete_recipe(db: Session, recipe_id: int) -> bool:
	recipe = db.get(Recipe, recipe_id)
	if recipe is None:
		return False
	photos.delete_recipe_photos(db, recipe)
	db.delete(recipe)
	db.commit()
	return True


def split_terms(terms: list[str] | None) -> list[str]:
	return [t.strip() for t in terms or [] if t and t.strip()]


def tag_exists(name: str):
	return exists().where(
		RecipeTag.recipe_id == Recipe.id,
		RecipeTag.tag_id == Tag.id,
		func.lower(Tag.name) == name.lower(),
	)


def ingredient_exists(own, term: str):
	return exists().where(
		Ingredient.version_id == own.id,
		Ingredient.name.ilike(f"%{term}%"),
	)


def text_matches(own, q: str):
	pattern = f"%{q}%"
	in_notes = exists().where(
		Note.recipe_id == Recipe.id,
		Note.text.ilike(pattern),
	)
	return or_(own.title.ilike(pattern), own.intro.ilike(pattern),
		   in_notes)


def cook_stats():
	"""Correlated scalar subqueries: (count, last cooked_on)."""
	base = select(CookLog).where(CookLog.recipe_id == Recipe.id)
	count = base.with_only_columns(func.count(CookLog.id))
	last = base.with_only_columns(func.max(CookLog.cooked_on))
	return count.scalar_subquery(), last.scalar_subquery()


def first_photo_id():
	"""Correlated scalar subquery: id of the oldest photo or NULL."""
	return (
		select(Photo.id)
		.where(Photo.recipe_id == Recipe.id)
		.order_by(Photo.created_at, Photo.id)
		.limit(1)
		.scalar_subquery()
	)


def thumb_url(photo_id: int | None) -> str | None:
	if photo_id is None:
		return None
	return storage.media_url(storage.photo_name(photo_id, thumb=True))


def list_recipes(db: Session, q: str | None = None,
		 category_id: int | None = None,
		 tags: list[str] | None = None,
		 ingredients: list[str] | None = None,
		 favorite: bool | None = None) -> list[dict]:
	"""Return RecipeListItem-shaped dicts ordered by the own title."""
	own = aliased(RecipeVersion)
	cooked_count, last_cooked = cook_stats()
	stmt = (
		select(Recipe, own.title, cooked_count, last_cooked,
		       first_photo_id())
		.join(own, (own.recipe_id == Recipe.id)
		      & (own.kind == VersionKind.OWN))
		.options(selectinload(Recipe.category),
			 selectinload(Recipe.tags))
		.order_by(func.lower(own.title), Recipe.id)
	)
	if q and q.strip():
		stmt = stmt.where(text_matches(own, q.strip()))
	if category_id is not None:
		stmt = stmt.where(Recipe.category_id == category_id)
	for name in split_terms(tags):
		stmt = stmt.where(tag_exists(name))
	for term in split_terms(ingredients):
		stmt = stmt.where(ingredient_exists(own, term))
	if favorite is not None:
		stmt = stmt.where(Recipe.favorite.is_(favorite))
	return [list_item(*row) for row in db.execute(stmt)]


def list_item(recipe: Recipe, title: str, cooked_count: int,
	      last_cooked, photo_id: int | None) -> dict:
	return {
		"id": recipe.id,
		"title": title,
		"category": recipe.category,
		"tags": [t.name for t in recipe.tags],
		"favorite": recipe.favorite,
		"thumb_url": thumb_url(photo_id),
		"cooked_count": cooked_count,
		"last_cooked": last_cooked,
		"updated_at": recipe.updated_at,
	}
