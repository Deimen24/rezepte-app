"""SQLAlchemy models. Schema changes go through Alembic migrations."""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
	Boolean,
	Date,
	DateTime,
	Enum,
	ForeignKey,
	Integer,
	Numeric,
	String,
	Text,
	UniqueConstraint,
	func,
)
from sqlalchemy.orm import (
	DeclarativeBase,
	Mapped,
	mapped_column,
	relationship,
)

NAME_LEN = 200
UNIT_LEN = 50
FILENAME_LEN = 255


class Base(DeclarativeBase):
	pass


class SourceKind(str, enum.Enum):
	URL = "url"
	BOOK = "book"
	NONE = "none"


class VersionKind(str, enum.Enum):
	ORIGINAL = "original"
	OWN = "own"


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = mapped_column(primary_key=True)
	username: Mapped[str] = mapped_column(String(NAME_LEN), unique=True)
	password_hash: Mapped[str] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now())

	sessions: Mapped[list["Session"]] = relationship(
		back_populates="user", cascade="all, delete-orphan")


class Session(Base):
	__tablename__ = "sessions"

	id: Mapped[int] = mapped_column(primary_key=True)
	user_id: Mapped[int] = mapped_column(
		ForeignKey("users.id", ondelete="CASCADE"))
	token_hash: Mapped[str] = mapped_column(String(128), unique=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now())
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

	user: Mapped["User"] = relationship(back_populates="sessions")


class Category(Base):
	__tablename__ = "categories"

	id: Mapped[int] = mapped_column(primary_key=True)
	name: Mapped[str] = mapped_column(String(NAME_LEN), unique=True)


class Tag(Base):
	__tablename__ = "tags"

	id: Mapped[int] = mapped_column(primary_key=True)
	name: Mapped[str] = mapped_column(String(NAME_LEN), unique=True)


class RecipeTag(Base):
	__tablename__ = "recipe_tags"

	recipe_id: Mapped[int] = mapped_column(
		ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True)
	tag_id: Mapped[int] = mapped_column(
		ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class Recipe(Base):
	__tablename__ = "recipes"

	id: Mapped[int] = mapped_column(primary_key=True)
	category_id: Mapped[int | None] = mapped_column(
		ForeignKey("categories.id", ondelete="SET NULL"))
	source_kind: Mapped[SourceKind] = mapped_column(
		Enum(SourceKind, name="source_kind"), default=SourceKind.NONE)
	source_url: Mapped[str | None] = mapped_column(Text)
	source_book: Mapped[str | None] = mapped_column(String(NAME_LEN))
	source_page: Mapped[str | None] = mapped_column(String(UNIT_LEN))
	favorite: Mapped[bool] = mapped_column(Boolean, default=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(),
		onupdate=func.now())

	category: Mapped["Category | None"] = relationship()
	tags: Mapped[list["Tag"]] = relationship(
		secondary="recipe_tags", order_by="Tag.name")
	versions: Mapped[list["RecipeVersion"]] = relationship(
		back_populates="recipe", cascade="all, delete-orphan")
	notes: Mapped[list["Note"]] = relationship(
		back_populates="recipe", cascade="all, delete-orphan",
		order_by="Note.created_at.desc()")
	cook_log: Mapped[list["CookLog"]] = relationship(
		back_populates="recipe", cascade="all, delete-orphan",
		order_by="CookLog.cooked_on.desc()")
	photos: Mapped[list["Photo"]] = relationship(
		back_populates="recipe", cascade="all, delete-orphan",
		order_by="Photo.created_at")

	def version(self, kind: VersionKind) -> "RecipeVersion | None":
		for v in self.versions:
			if v.kind == kind:
				return v
		return None

	@property
	def original(self) -> "RecipeVersion | None":
		return self.version(VersionKind.ORIGINAL)

	@property
	def own(self) -> "RecipeVersion | None":
		return self.version(VersionKind.OWN)


class RecipeVersion(Base):
	__tablename__ = "recipe_versions"
	__table_args__ = (
		UniqueConstraint("recipe_id", "kind", name="uq_version_kind"),
	)

	id: Mapped[int] = mapped_column(primary_key=True)
	recipe_id: Mapped[int] = mapped_column(
		ForeignKey("recipes.id", ondelete="CASCADE"))
	kind: Mapped[VersionKind] = mapped_column(
		Enum(VersionKind, name="version_kind"))
	title: Mapped[str] = mapped_column(String(NAME_LEN))
	intro: Mapped[str] = mapped_column(Text, default="")
	servings: Mapped[int | None] = mapped_column(Integer)
	prep_minutes: Mapped[int | None] = mapped_column(Integer)
	cook_minutes: Mapped[int | None] = mapped_column(Integer)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(),
		onupdate=func.now())

	recipe: Mapped["Recipe"] = relationship(back_populates="versions")
	ingredients: Mapped[list["Ingredient"]] = relationship(
		back_populates="version", cascade="all, delete-orphan",
		order_by="Ingredient.position")
	steps: Mapped[list["Step"]] = relationship(
		back_populates="version", cascade="all, delete-orphan",
		order_by="Step.position")


class Ingredient(Base):
	__tablename__ = "ingredients"

	id: Mapped[int] = mapped_column(primary_key=True)
	version_id: Mapped[int] = mapped_column(
		ForeignKey("recipe_versions.id", ondelete="CASCADE"))
	position: Mapped[int] = mapped_column(Integer)
	amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
	unit: Mapped[str] = mapped_column(String(UNIT_LEN), default="")
	name: Mapped[str] = mapped_column(String(NAME_LEN))
	note: Mapped[str] = mapped_column(String(NAME_LEN), default="")

	version: Mapped["RecipeVersion"] = relationship(
		back_populates="ingredients")


class Step(Base):
	__tablename__ = "steps"

	id: Mapped[int] = mapped_column(primary_key=True)
	version_id: Mapped[int] = mapped_column(
		ForeignKey("recipe_versions.id", ondelete="CASCADE"))
	position: Mapped[int] = mapped_column(Integer)
	text: Mapped[str] = mapped_column(Text)

	version: Mapped["RecipeVersion"] = relationship(back_populates="steps")


class Note(Base):
	__tablename__ = "notes"

	id: Mapped[int] = mapped_column(primary_key=True)
	recipe_id: Mapped[int] = mapped_column(
		ForeignKey("recipes.id", ondelete="CASCADE"))
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now())
	text: Mapped[str] = mapped_column(Text)

	recipe: Mapped["Recipe"] = relationship(back_populates="notes")


class CookLog(Base):
	__tablename__ = "cook_log"

	id: Mapped[int] = mapped_column(primary_key=True)
	recipe_id: Mapped[int] = mapped_column(
		ForeignKey("recipes.id", ondelete="CASCADE"))
	cooked_on: Mapped[date] = mapped_column(Date)
	rating: Mapped[int | None] = mapped_column(Integer)
	comment: Mapped[str] = mapped_column(Text, default="")

	recipe: Mapped["Recipe"] = relationship(back_populates="cook_log")


class Photo(Base):
	__tablename__ = "photos"

	id: Mapped[int] = mapped_column(primary_key=True)
	recipe_id: Mapped[int] = mapped_column(
		ForeignKey("recipes.id", ondelete="CASCADE"))
	filename: Mapped[str] = mapped_column(String(FILENAME_LEN))
	is_own_result: Mapped[bool] = mapped_column(Boolean, default=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now())

	recipe: Mapped["Recipe"] = relationship(back_populates="photos")
