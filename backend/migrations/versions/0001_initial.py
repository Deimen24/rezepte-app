"""initial schema: all tables for phases 1-3

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NAME_LEN = 200
UNIT_LEN = 50
FILENAME_LEN = 255
TOKEN_HASH_LEN = 128

# SQLAlchemy stores the member names of a Python enum, not its values.
SOURCE_KIND = sa.Enum("URL", "BOOK", "NONE", name="source_kind")
VERSION_KIND = sa.Enum("ORIGINAL", "OWN", name="version_kind")


def _id():
	return sa.Column("id", sa.Integer, primary_key=True)


def _now(name):
	return sa.Column(name, sa.DateTime(timezone=True),
			 server_default=sa.func.now(), nullable=False)


def _fk(name, target, ondelete, nullable=False):
	return sa.Column(name, sa.Integer,
			 sa.ForeignKey(target, ondelete=ondelete),
			 nullable=nullable)


def _index(table, col):
	op.create_index("ix_%s_%s" % (table, col), table, [col])


def _users():
	op.create_table("users",
		_id(),
		sa.Column("username", sa.String(NAME_LEN), nullable=False,
			  unique=True),
		sa.Column("password_hash", sa.Text, nullable=False),
		_now("created_at"))


def _sessions():
	op.create_table("sessions",
		_id(),
		_fk("user_id", "users.id", "CASCADE"),
		sa.Column("token_hash", sa.String(TOKEN_HASH_LEN),
			  nullable=False, unique=True),
		_now("created_at"),
		sa.Column("expires_at", sa.DateTime(timezone=True),
			  nullable=False))
	_index("sessions", "user_id")


def _taxonomy():
	for table in ("categories", "tags"):
		op.create_table(table,
			_id(),
			sa.Column("name", sa.String(NAME_LEN),
				  nullable=False, unique=True))


def _recipes():
	op.create_table("recipes",
		_id(),
		_fk("category_id", "categories.id", "SET NULL",
		    nullable=True),
		sa.Column("source_kind", SOURCE_KIND, nullable=False),
		sa.Column("source_url", sa.Text),
		sa.Column("source_book", sa.String(NAME_LEN)),
		sa.Column("source_page", sa.String(UNIT_LEN)),
		sa.Column("favorite", sa.Boolean, nullable=False),
		_now("created_at"),
		_now("updated_at"))
	_index("recipes", "category_id")


def _recipe_tags():
	op.create_table("recipe_tags",
		sa.Column("recipe_id", sa.Integer,
			  sa.ForeignKey("recipes.id", ondelete="CASCADE"),
			  primary_key=True),
		sa.Column("tag_id", sa.Integer,
			  sa.ForeignKey("tags.id", ondelete="CASCADE"),
			  primary_key=True))
	_index("recipe_tags", "tag_id")


def _versions():
	op.create_table("recipe_versions",
		_id(),
		_fk("recipe_id", "recipes.id", "CASCADE"),
		sa.Column("kind", VERSION_KIND, nullable=False),
		sa.Column("title", sa.String(NAME_LEN), nullable=False),
		sa.Column("intro", sa.Text, nullable=False),
		sa.Column("servings", sa.Integer),
		sa.Column("prep_minutes", sa.Integer),
		sa.Column("cook_minutes", sa.Integer),
		_now("created_at"),
		_now("updated_at"),
		sa.UniqueConstraint("recipe_id", "kind",
				    name="uq_version_kind"))
	_index("recipe_versions", "recipe_id")


def _ingredients():
	op.create_table("ingredients",
		_id(),
		_fk("version_id", "recipe_versions.id", "CASCADE"),
		sa.Column("position", sa.Integer, nullable=False),
		sa.Column("amount", sa.Numeric(10, 3)),
		sa.Column("unit", sa.String(UNIT_LEN), nullable=False),
		sa.Column("name", sa.String(NAME_LEN), nullable=False),
		sa.Column("note", sa.String(NAME_LEN), nullable=False))
	_index("ingredients", "version_id")


def _steps():
	op.create_table("steps",
		_id(),
		_fk("version_id", "recipe_versions.id", "CASCADE"),
		sa.Column("position", sa.Integer, nullable=False),
		sa.Column("text", sa.Text, nullable=False))
	_index("steps", "version_id")


def _notes():
	op.create_table("notes",
		_id(),
		_fk("recipe_id", "recipes.id", "CASCADE"),
		_now("created_at"),
		sa.Column("text", sa.Text, nullable=False))
	_index("notes", "recipe_id")


def _cook_log():
	op.create_table("cook_log",
		_id(),
		_fk("recipe_id", "recipes.id", "CASCADE"),
		sa.Column("cooked_on", sa.Date, nullable=False),
		sa.Column("rating", sa.Integer),
		sa.Column("comment", sa.Text, nullable=False))
	_index("cook_log", "recipe_id")


def _photos():
	op.create_table("photos",
		_id(),
		_fk("recipe_id", "recipes.id", "CASCADE"),
		sa.Column("filename", sa.String(FILENAME_LEN),
			  nullable=False),
		sa.Column("is_own_result", sa.Boolean, nullable=False),
		_now("created_at"))
	_index("photos", "recipe_id")


# Drop order is the reverse of creation (children first).
TABLES = ("photos", "cook_log", "notes", "steps", "ingredients",
	  "recipe_versions", "recipe_tags", "recipes", "tags",
	  "categories", "sessions", "users")


def upgrade() -> None:
	_users()
	_sessions()
	_taxonomy()
	_recipes()
	_recipe_tags()
	_versions()
	_ingredients()
	_steps()
	_notes()
	_cook_log()
	_photos()


def downgrade() -> None:
	for table in TABLES:
		op.drop_table(table)
	bind = op.get_bind()
	VERSION_KIND.drop(bind, checkfirst=True)
	SOURCE_KIND.drop(bind, checkfirst=True)
