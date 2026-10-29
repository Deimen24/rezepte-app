"""Categories and tags: list and create, names unique ignoring case."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Tag


def clean_name(name: str) -> str:
	name = (name or "").strip()
	if not name:
		raise ValueError("name must not be empty")
	return name


def find_by_name(db: Session, model, name: str):
	stmt = select(model).where(func.lower(model.name) == name.lower())
	return db.scalars(stmt).first()


def list_categories(db: Session) -> list[Category]:
	stmt = select(Category).order_by(Category.name)
	return list(db.scalars(stmt))


def create_category(db: Session, name: str) -> Category:
	name = clean_name(name)
	cat = find_by_name(db, Category, name)
	if cat is not None:
		return cat
	cat = Category(name=name)
	db.add(cat)
	db.commit()
	db.refresh(cat)
	return cat


def list_tags(db: Session) -> list[Tag]:
	stmt = select(Tag).order_by(Tag.name)
	return list(db.scalars(stmt))


def create_tag(db: Session, name: str) -> Tag:
	name = clean_name(name)
	tag = find_by_name(db, Tag, name)
	if tag is not None:
		return tag
	tag = Tag(name=name)
	db.add(tag)
	db.commit()
	db.refresh(tag)
	return tag


def get_or_create_tags(db: Session, names: list[str]) -> list[Tag]:
	"""Resolve tag names to Tag rows, creating missing ones (no commit)."""
	tags: list[Tag] = []
	for raw in names:
		name = (raw or "").strip()
		if not name:
			continue
		if any(t.name.lower() == name.lower() for t in tags):
			continue
		tag = find_by_name(db, Tag, name)
		if tag is None:
			tag = Tag(name=name)
			db.add(tag)
			db.flush()
		tags.append(tag)
	return tags
