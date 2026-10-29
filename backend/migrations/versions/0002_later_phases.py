"""share token, nutrition, shopping list, pantry, integrations

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NAME_LEN = 200
UNIT_LEN = 50
TOKEN_LEN = 64

PANTRY_DEFAULTS = ("Salz", "Pfeffer", "Olivenöl", "Öl", "Wasser",
		   "Zucker", "Mehl", "Butter", "Essig")

NUTRITION = ("kcal", "protein_g", "carbs_g", "fat_g")


def _now(name):
	return sa.Column(name, sa.DateTime(timezone=True),
			 server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
	with op.batch_alter_table("recipes") as b:
		b.add_column(sa.Column("share_token", sa.String(TOKEN_LEN)))
		b.create_unique_constraint("uq_recipes_share_token",
					   ["share_token"])
	with op.batch_alter_table("recipe_versions") as b:
		for col in NUTRITION:
			b.add_column(sa.Column(col, sa.Numeric(8, 1)))

	op.create_table(
		"shopping_items",
		sa.Column("id", sa.Integer, primary_key=True),
		sa.Column("name", sa.String(NAME_LEN), nullable=False),
		sa.Column("unit", sa.String(UNIT_LEN), nullable=False),
		sa.Column("amount", sa.Numeric(10, 3)),
		sa.Column("note", sa.String(NAME_LEN), nullable=False),
		sa.Column("checked", sa.Boolean, nullable=False),
		sa.Column("recipe_id", sa.Integer,
			  sa.ForeignKey("recipes.id", ondelete="SET NULL")),
		_now("created_at"),
	)
	op.create_index("ix_shopping_items_recipe_id", "shopping_items",
			["recipe_id"])

	pantry = op.create_table(
		"pantry",
		sa.Column("id", sa.Integer, primary_key=True),
		sa.Column("name", sa.String(NAME_LEN), nullable=False,
			  unique=True),
	)
	op.bulk_insert(pantry, [{"name": n} for n in PANTRY_DEFAULTS])

	op.create_table(
		"integrations",
		sa.Column("id", sa.Integer, primary_key=True),
		sa.Column("name", sa.String(NAME_LEN), nullable=False,
			  unique=True),
		sa.Column("data", sa.Text, nullable=False),
		_now("updated_at"),
	)


def downgrade() -> None:
	op.drop_table("integrations")
	op.drop_table("pantry")
	op.drop_index("ix_shopping_items_recipe_id", "shopping_items")
	op.drop_table("shopping_items")
	with op.batch_alter_table("recipe_versions") as b:
		for col in NUTRITION:
			b.drop_column(col)
	with op.batch_alter_table("recipes") as b:
		b.drop_constraint("uq_recipes_share_token", type_="unique")
		b.drop_column("share_token")
