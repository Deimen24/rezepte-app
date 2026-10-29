"""The Alembic migration must produce the same schema as the models."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Base, Recipe, RecipeVersion, SourceKind, VersionKind

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = BACKEND_DIR / "migrations"
VERSION_TABLE = "alembic_version"


def alembic_config() -> Config:
	cfg = Config()
	cfg.set_main_option("script_location", str(SCRIPTS))
	return cfg


def file_url(path: Path) -> str:
	return "sqlite:///" + str(path)


@pytest.fixture
def migrated(tmp_path, monkeypatch):
	"""Engine on a file database built by `alembic upgrade head`."""
	url = file_url(tmp_path / "migrated.db")
	# env.py reads settings.database_url when the migration runs.
	monkeypatch.setattr(settings, "database_url", url)
	command.upgrade(alembic_config(), "head")
	engine = create_engine(url)
	yield engine
	engine.dispose()


@pytest.fixture
def from_models(tmp_path):
	"""Engine on a file database built by Base.metadata.create_all."""
	engine = create_engine(file_url(tmp_path / "models.db"))
	Base.metadata.create_all(engine)
	yield engine
	engine.dispose()


def app_tables(engine) -> set[str]:
	return set(inspect(engine).get_table_names()) - {VERSION_TABLE}


def columns(engine, table) -> dict:
	"""name -> (type affinity, nullable); lengths/scales are not kept
	by SQLite reflection beyond the type name, so compare str(type)."""
	return {
		c["name"]: (str(c["type"]), c["nullable"])
		for c in inspect(engine).get_columns(table)
	}


def foreign_keys(engine, table) -> list:
	keys = [
		(tuple(fk["constrained_columns"]), fk["referred_table"],
		 tuple(fk["referred_columns"]), fk["options"].get("ondelete"))
		for fk in inspect(engine).get_foreign_keys(table)
	]
	return sorted(keys)


def unique_constraints(engine, table) -> list:
	cons = [tuple(u["column_names"])
		for u in inspect(engine).get_unique_constraints(table)]
	return sorted(cons)


def primary_key(engine, table) -> list:
	return inspect(engine).get_pk_constraint(table)["constrained_columns"]


def test_upgrade_creates_all_model_tables(migrated, from_models):
	assert app_tables(migrated) == app_tables(from_models)
	assert app_tables(migrated) == set(Base.metadata.tables)


def test_upgrade_records_head_revision(migrated):
	with migrated.connect() as conn:
		rows = conn.execute(text("SELECT version_num FROM %s"
					 % VERSION_TABLE)).all()
	assert rows == [("0001",)]


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
def test_columns_match_models(migrated, from_models, table):
	assert columns(migrated, table) == columns(from_models, table)


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
def test_foreign_keys_match_models(migrated, from_models, table):
	assert foreign_keys(migrated, table) == \
		foreign_keys(from_models, table)


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
def test_unique_constraints_match_models(migrated, from_models, table):
	assert unique_constraints(migrated, table) == \
		unique_constraints(from_models, table)


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
def test_primary_keys_match_models(migrated, from_models, table):
	assert primary_key(migrated, table) == primary_key(from_models, table)


def test_cascade_rules_as_planned(migrated):
	"""Spot check the ON DELETE rules the plan promises."""
	fks = {t: foreign_keys(migrated, t) for t in app_tables(migrated)}
	assert fks["recipes"] == [(("category_id",), "categories", ("id",),
				   "SET NULL")]
	assert fks["recipe_versions"] == [(("recipe_id",), "recipes",
					   ("id",), "CASCADE")]
	assert fks["sessions"] == [(("user_id",), "users", ("id",),
				    "CASCADE")]
	for child in ("ingredients", "steps"):
		assert fks[child] == [(("version_id",), "recipe_versions",
				       ("id",), "CASCADE")]
	for child in ("notes", "cook_log", "photos"):
		assert fks[child] == [(("recipe_id",), "recipes", ("id",),
				       "CASCADE")]


def test_migrated_schema_stores_enum_member_names(migrated):
	"""The ORM writes enum member names (NONE, OWN), and the migration
	declares exactly those; a mismatch would only show on PostgreSQL,
	so check the raw value the ORM writes into the migrated schema."""
	with Session(migrated) as db:
		recipe = Recipe(source_kind=SourceKind.NONE, favorite=False)
		recipe.versions.append(RecipeVersion(kind=VersionKind.OWN,
						     title="t", intro=""))
		db.add(recipe)
		db.commit()
		raw = db.execute(text("SELECT source_kind FROM recipes")) \
			.scalar_one()
		kind = db.execute(text("SELECT kind FROM recipe_versions")) \
			.scalar_one()
	assert raw == "NONE"
	assert kind == "OWN"
	assert raw in SourceKind.__members__
	with Session(migrated) as db:
		loaded = db.scalar(select(Recipe))
		assert loaded.source_kind is SourceKind.NONE


def test_downgrade_base_removes_all_tables(migrated):
	# Alembic keeps its own bookkeeping table after a full downgrade;
	# every application table must be gone.
	command.downgrade(alembic_config(), "base")
	assert app_tables(migrated) == set()
	assert set(inspect(migrated).get_table_names()) <= {VERSION_TABLE}


def test_upgrade_is_idempotent_at_head(migrated):
	before = app_tables(migrated)
	command.upgrade(alembic_config(), "head")
	assert app_tables(migrated) == before
