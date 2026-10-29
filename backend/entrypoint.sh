#!/bin/sh
# Wait for the database, apply migrations, then run the given command.
set -e

DB_WAIT_SECONDS=${DB_WAIT_SECONDS:-60}

python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text
from app.config import settings

limit = int(os.environ.get("DB_WAIT_SECONDS", "60"))
engine = create_engine(settings.database_url)
for i in range(limit):
	try:
		with engine.connect() as conn:
			conn.execute(text("SELECT 1"))
		print("database ready")
		break
	except Exception as exc:
		if i == limit - 1:
			print("database not reachable:", exc, file=sys.stderr)
			sys.exit(1)
		time.sleep(1)
PY

alembic upgrade head

exec "$@"
