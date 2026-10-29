"""Pydantic models for the JSON API (see docs/PLAN.md, "JSON-Formen")."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
	BaseModel,
	ConfigDict,
	Field,
	field_serializer,
	field_validator,
	model_validator,
)

from app.models import NAME_LEN, UNIT_LEN

SourceKindName = Literal["url", "book", "none"]


def amount_to_str(value: Decimal | None) -> str | None:
	"""Render a Decimal without trailing zeros, e.g. 0.500 -> "0.5"."""
	if value is None:
		return None
	text = format(value, "f")
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return text or "0"


class IngredientIn(BaseModel):
	amount: Decimal | None = None
	unit: str = Field(default="", max_length=UNIT_LEN)
	name: str = Field(min_length=1, max_length=NAME_LEN)
	note: str = Field(default="", max_length=NAME_LEN)

	@field_validator("name", "unit", "note", mode="before")
	@classmethod
	def strip_text(cls, value):
		if value is None:
			return ""
		return value.strip() if isinstance(value, str) else value


class IngredientOut(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	amount: Decimal | None = None
	unit: str = ""
	name: str
	note: str = ""

	@field_serializer("amount")
	def serialize_amount(self, value: Decimal | None) -> str | None:
		return amount_to_str(value)


class StepIn(BaseModel):
	text: str = Field(min_length=1)

	@field_validator("text", mode="before")
	@classmethod
	def strip_text(cls, value):
		return value.strip() if isinstance(value, str) else value


class StepOut(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	text: str


class VersionIn(BaseModel):
	title: str = Field(min_length=1, max_length=NAME_LEN)
	intro: str = ""
	servings: int | None = Field(default=None, ge=0)
	prep_minutes: int | None = Field(default=None, ge=0)
	cook_minutes: int | None = Field(default=None, ge=0)
	ingredients: list[IngredientIn] = []
	steps: list[StepIn] = []

	@field_validator("title", "intro", mode="before")
	@classmethod
	def strip_text(cls, value):
		if value is None:
			return ""
		return value.strip() if isinstance(value, str) else value


class VersionOut(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	title: str
	intro: str = ""
	servings: int | None = None
	prep_minutes: int | None = None
	cook_minutes: int | None = None
	ingredients: list[IngredientOut] = []
	steps: list[StepOut] = []


class Source(BaseModel):
	kind: SourceKindName = "none"
	url: str | None = None
	book: str | None = Field(default=None, max_length=NAME_LEN)
	page: str | None = Field(default=None, max_length=UNIT_LEN)

	@field_validator("url", "book", "page", mode="before")
	@classmethod
	def empty_to_none(cls, value):
		if isinstance(value, str):
			value = value.strip()
			return value or None
		return value

	@model_validator(mode="after")
	def check_kind(self):
		if self.kind == "url" and not self.url:
			raise ValueError("source kind 'url' needs a url")
		if self.kind == "book" and not self.book:
			raise ValueError("source kind 'book' needs a book")
		return self


class CategoryIn(BaseModel):
	name: str = Field(min_length=1, max_length=NAME_LEN)


class CategoryOut(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	name: str


class TagIn(BaseModel):
	name: str = Field(min_length=1, max_length=NAME_LEN)


class TagOut(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	name: str


class RecipeInput(BaseModel):
	category_id: int | None = None
	tags: list[str] = []
	favorite: bool = False
	source: Source = Source()
	version: VersionIn

	@field_validator("tags")
	@classmethod
	def clean_tags(cls, value: list[str]) -> list[str]:
		seen: list[str] = []
		lower: set[str] = set()
		for name in value:
			name = name.strip()
			if name and name.lower() not in lower:
				seen.append(name)
				lower.add(name.lower())
		return seen


NOTE_MAX = 5000
COMMENT_MAX = 2000
RATING_MIN = 1
RATING_MAX = 5


class NoteIn(BaseModel):
	text: str = Field(min_length=1, max_length=NOTE_MAX)

	@field_validator("text", mode="before")
	@classmethod
	def strip_text(cls, value):
		return value.strip() if isinstance(value, str) else value


class NoteOut(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	created_at: datetime
	text: str


class CookLogIn(BaseModel):
	cooked_on: date
	rating: int | None = Field(default=None, ge=RATING_MIN, le=RATING_MAX)
	comment: str = Field(default="", max_length=COMMENT_MAX)

	@field_validator("comment", mode="before")
	@classmethod
	def strip_text(cls, value):
		if value is None:
			return ""
		return value.strip() if isinstance(value, str) else value


class CookLogOut(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	cooked_on: date
	rating: int | None
	comment: str


class FavoriteIn(BaseModel):
	favorite: bool


class FavoriteOut(BaseModel):
	favorite: bool


class PhotoOut(BaseModel):
	id: int
	url: str
	thumb_url: str
	is_own_result: bool
	created_at: datetime


class RecipeOut(BaseModel):
	id: int
	category: CategoryOut | None
	tags: list[str]
	favorite: bool
	source: Source
	original: VersionOut
	own: VersionOut
	notes: list[NoteOut]
	cook_log: list[CookLogOut]
	photos: list[PhotoOut]
	created_at: datetime
	updated_at: datetime


class RecipeListItem(BaseModel):
	id: int
	title: str
	category: CategoryOut | None
	tags: list[str]
	favorite: bool
	thumb_url: str | None
	cooked_count: int
	last_cooked: date | None
	updated_at: datetime
