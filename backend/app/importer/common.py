"""Intermediate result shared by the JSON-LD and heuristic extractors."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class RecipeData:
	title: str = ""
	intro: str = ""
	servings: int | None = None
	prep_minutes: int | None = None
	cook_minutes: int | None = None
	ingredient_lines: list[str] = field(default_factory=list)
	steps: list[str] = field(default_factory=list)
	image_url: str | None = None
	kcal: Decimal | None = None
	protein_g: Decimal | None = None
	carbs_g: Decimal | None = None
	fat_g: Decimal | None = None
	warnings: list[str] = field(default_factory=list)

	def is_usable(self) -> bool:
		has_body = self.ingredient_lines or self.steps
		return bool(self.title and has_body)
