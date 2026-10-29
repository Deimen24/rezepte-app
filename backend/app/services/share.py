"""Public sharing of one recipe by an unguessable token."""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Photo, Recipe, RecipeVersion, VersionKind
from app.schemas import SharedRecipe, VersionOut

TOKEN_BYTES = 32
SHARE_PATH_PREFIX = "/#/s/"
SHARE_PHOTO_PREFIX = "/share/"

LOAD_SHARED = (
	selectinload(Recipe.category),
	selectinload(Recipe.tags),
	selectinload(Recipe.versions).selectinload(RecipeVersion.ingredients),
	selectinload(Recipe.versions).selectinload(RecipeVersion.steps),
	selectinload(Recipe.photos),
)


def new_token() -> str:
	return secrets.token_urlsafe(TOKEN_BYTES)


def share_path(token: str) -> str:
	return SHARE_PATH_PREFIX + token


def photo_url(token: str, photo_id: int) -> str:
	return "%s%s/photos/%d.jpg" % (SHARE_PHOTO_PREFIX, token, photo_id)


def enable(db: Session, recipe_id: int) -> Recipe | None:
	"""Idempotent: an existing token is kept."""
	recipe = db.get(Recipe, recipe_id)
	if recipe is None:
		return None
	if recipe.share_token is None:
		recipe.share_token = new_token()
		db.commit()
	return recipe


def disable(db: Session, recipe_id: int) -> Recipe | None:
	recipe = db.get(Recipe, recipe_id)
	if recipe is None:
		return None
	if recipe.share_token is not None:
		recipe.share_token = None
		db.commit()
	return recipe


def get_shared(db: Session, token: str) -> Recipe | None:
	if not token:
		return None
	stmt = (
		select(Recipe)
		.where(Recipe.share_token == token)
		.options(*LOAD_SHARED)
		.execution_options(populate_existing=True)
	)
	return db.scalars(stmt).first()


def shared_photo(db: Session, token: str, photo_id: int) -> Photo | None:
	"""The photo only if it belongs to the recipe behind the token."""
	if not token:
		return None
	stmt = (
		select(Photo)
		.join(Recipe, Recipe.id == Photo.recipe_id)
		.where(Recipe.share_token == token, Photo.id == photo_id)
	)
	return db.scalars(stmt).first()


def to_shared(recipe: Recipe) -> SharedRecipe:
	own = recipe.version(VersionKind.OWN)
	rows = sorted(recipe.photos, key=lambda p: (p.created_at, p.id))
	return SharedRecipe(
		title=own.title,
		category=recipe.category.name if recipe.category else None,
		tags=[t.name for t in recipe.tags],
		own=VersionOut.model_validate(own),
		photos=[photo_url(recipe.share_token, p.id) for p in rows],
	)
