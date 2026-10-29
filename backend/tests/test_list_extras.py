"""List items: thumb_url, cooked_count, last_cooked without N+1."""

from datetime import date, datetime, timezone

from sqlalchemy import event

from app.models import CookLog, Photo


def recipe(title):
	return {"tags": ["vegi"], "source": {"kind": "none"},
		"version": {"title": title, "steps": [{"text": "Kochen."}]}}


def post(client, title):
	resp = client.post("/api/recipes", json=recipe(title))
	assert resp.status_code == 201, resp.text
	return resp.json()["id"]


def items(client):
	resp = client.get("/api/recipes")
	assert resp.status_code == 200, resp.text
	return {r["id"]: r for r in resp.json()}


def at(day):
	return datetime(2026, 10, day, 12, 0, tzinfo=timezone.utc)


def test_without_extras(auth_client):
	rid = post(auth_client, "Brot")
	item = items(auth_client)[rid]
	assert item["thumb_url"] is None
	assert item["cooked_count"] == 0
	assert item["last_cooked"] is None


def test_thumb_is_first_photo_by_created_at(auth_client, db):
	rid = post(auth_client, "Brot")
	later = Photo(recipe_id=rid, filename="a.jpg", created_at=at(5))
	first = Photo(recipe_id=rid, filename="b.jpg", created_at=at(2))
	db.add_all([later, first])
	db.commit()
	assert later.id < first.id
	item = items(auth_client)[rid]
	assert item["thumb_url"] == "/media/%d_t.jpg" % first.id


def test_cook_log_stats(auth_client, db):
	rid = post(auth_client, "Brot")
	other = post(auth_client, "Suppe")
	db.add_all([
		CookLog(recipe_id=rid, cooked_on=date(2026, 9, 1)),
		CookLog(recipe_id=rid, cooked_on=date(2026, 10, 7)),
		CookLog(recipe_id=rid, cooked_on=date(2026, 3, 3)),
		CookLog(recipe_id=other, cooked_on=date(2026, 1, 1)),
	])
	db.commit()
	got = items(auth_client)
	assert got[rid]["cooked_count"] == 3
	assert got[rid]["last_cooked"] == "2026-10-07"
	assert got[other]["cooked_count"] == 1
	assert got[other]["last_cooked"] == "2026-01-01"


def seed(client, db, n):
	for i in range(n):
		rid = post(client, "Rezept %d" % i)
		db.add(CookLog(recipe_id=rid, cooked_on=date(2026, 1, 1)))
		db.add(Photo(recipe_id=rid, filename="p.jpg"))
	db.commit()


def count_statements(client, db) -> int:
	engine = db.get_bind()
	calls = []

	def tick(*args):
		calls.append(1)

	event.listen(engine, "before_cursor_execute", tick)
	try:
		assert client.get("/api/recipes").status_code == 200
	finally:
		event.remove(engine, "before_cursor_execute", tick)
	return len(calls)


def test_query_count_does_not_grow_with_recipes(auth_client, db):
	seed(auth_client, db, 2)
	small = count_statements(auth_client, db)
	seed(auth_client, db, 4)
	assert count_statements(auth_client, db) == small
