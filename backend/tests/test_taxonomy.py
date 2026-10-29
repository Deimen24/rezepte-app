"""Categories and tags: service and API, names unique ignoring case."""

import pytest

from app.services import taxonomy

CATEGORIES = "/api/categories"
TAGS = "/api/tags"


def post_name(client, path, name):
	return client.post(path, json={"name": name})


def names(client, path):
	resp = client.get(path)
	assert resp.status_code == 200, resp.text
	return [row["name"] for row in resp.json()]


@pytest.mark.parametrize("path", [CATEGORIES, TAGS])
def test_create_same_name_other_case_returns_same_id(auth_client, path):
	first = post_name(auth_client, path, "Vegi")
	second = post_name(auth_client, path, "vegi")
	assert first.status_code == 201, first.text
	assert second.status_code == 201, second.text
	assert first.json()["id"] == second.json()["id"]
	assert second.json()["name"] == "Vegi"
	assert names(auth_client, path) == ["Vegi"]


@pytest.mark.parametrize("path", [CATEGORIES, TAGS])
@pytest.mark.parametrize("bad", ["", "   ", None])
def test_create_empty_name_rejected(auth_client, path, bad):
	resp = post_name(auth_client, path, bad)
	assert resp.status_code == 422
	assert names(auth_client, path) == []


@pytest.mark.parametrize("path", [CATEGORIES, TAGS])
def test_create_missing_name_rejected(auth_client, path):
	resp = auth_client.post(path, json={})
	assert resp.status_code == 422


@pytest.mark.parametrize("path", [CATEGORIES, TAGS])
def test_create_name_too_long_rejected(auth_client, path):
	resp = post_name(auth_client, path, "x" * 201)
	assert resp.status_code == 422
	assert post_name(auth_client, path, "x" * 200).status_code == 201


@pytest.mark.parametrize("path", [CATEGORIES, TAGS])
def test_list_is_sorted_by_name(auth_client, path):
	for name in ("Suppen", "Desserts", "Hauptgang", "Apero"):
		assert post_name(auth_client, path, name).status_code == 201
	assert names(auth_client, path) == ["Apero", "Desserts",
					    "Hauptgang", "Suppen"]


@pytest.mark.parametrize("path", [CATEGORIES, TAGS])
def test_list_item_shape(auth_client, path):
	post_name(auth_client, path, "Vegi")
	rows = auth_client.get(path).json()
	assert len(rows) == 1
	assert set(rows[0]) == {"id", "name"}
	assert isinstance(rows[0]["id"], int)


@pytest.mark.parametrize("path", [CATEGORIES, TAGS])
def test_list_and_create_require_login(client, path):
	assert client.get(path).status_code == 401
	assert post_name(client, path, "Vegi").status_code == 401


def test_service_strips_whitespace_and_dedupes(db):
	first = taxonomy.create_category(db, "  Vegi ")
	second = taxonomy.create_category(db, "VEGI")
	assert first.name == "Vegi"
	assert first.id == second.id
	assert [c.name for c in taxonomy.list_categories(db)] == ["Vegi"]


def test_service_rejects_empty_name(db):
	with pytest.raises(ValueError):
		taxonomy.create_tag(db, "   ")
	with pytest.raises(ValueError):
		taxonomy.create_category(db, "")
	assert taxonomy.list_tags(db) == []


def test_service_get_or_create_tags_mixes_existing_and_new(db):
	existing = taxonomy.create_tag(db, "vegi")
	tags = taxonomy.get_or_create_tags(db, ["Vegi", " neu ", "", "NEU"])
	assert [t.name for t in tags] == ["vegi", "neu"]
	assert tags[0].id == existing.id
	db.commit()
	assert [t.name for t in taxonomy.list_tags(db)] == ["neu", "vegi"]


def test_categories_and_tags_are_separate_namespaces(db):
	cat = taxonomy.create_category(db, "Vegi")
	tag = taxonomy.create_tag(db, "Vegi")
	assert [c.name for c in taxonomy.list_categories(db)] == ["Vegi"]
	assert [t.name for t in taxonomy.list_tags(db)] == ["Vegi"]
	assert type(cat) is not type(tag)
