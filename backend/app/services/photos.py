"""Photo logic: process the upload, store files, keep rows in sync."""

from sqlalchemy.orm import Session

from app import images, storage
from app.models import Photo, Recipe
from app.schemas import PhotoOut

MAX_UPLOAD = 20 * 1024 * 1024


def _names(photo_id: int) -> tuple[str, str]:
	return (storage.photo_name(photo_id),
		storage.photo_name(photo_id, thumb=True))


def add_photo(db: Session, recipe_id: int, data: bytes,
	      is_own_result: bool) -> Photo | None:
	"""Store one upload. Raises ValueError if it is not an image;
	nothing is written in that case."""
	recipe = db.get(Recipe, recipe_id)
	if recipe is None:
		return None
	full, thumb = images.process(data)
	photo = Photo(recipe_id=recipe_id, filename="",
		      is_own_result=is_own_result)
	db.add(photo)
	db.flush()
	name, thumb_name = _names(photo.id)
	photo.filename = name
	storage.save(name, full)
	storage.save(thumb_name, thumb)
	db.commit()
	db.refresh(photo)
	return photo


def _remove_files(photo: Photo) -> None:
	for name in _names(photo.id):
		storage.delete(name)


def delete_photo(db: Session, recipe_id: int, photo_id: int) -> bool:
	photo = db.get(Photo, photo_id)
	if photo is None or photo.recipe_id != recipe_id:
		return False
	_remove_files(photo)
	db.delete(photo)
	db.commit()
	return True


def delete_recipe_photos(db: Session, recipe: Recipe) -> None:
	"""Remove the files of all photos; the rows go with the recipe."""
	for photo in recipe.photos:
		_remove_files(photo)


def to_out(photo: Photo) -> PhotoOut:
	return PhotoOut(
		id=photo.id,
		url=storage.media_url(photo.filename),
		thumb_url=storage.media_url(
			storage.photo_name(photo.id, thumb=True)),
		is_own_result=photo.is_own_result,
		created_at=photo.created_at,
	)
