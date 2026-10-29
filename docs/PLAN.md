# Plan und Stand

## Phase 1 – Fundament (in Arbeit)

### Dateien
    compose.yaml, compose.dev.yaml, .env.example, README.md, CLAUDE.md
    backend/Dockerfile, backend/requirements.txt, backend/entrypoint.sh
    backend/alembic.ini, backend/migrations/env.py,
    backend/migrations/versions/0001_initial.py
    backend/app/main.py config.py db.py models.py schemas.py auth.py
    backend/app/storage.py cli.py deps.py
    backend/app/services/{auth,recipes,taxonomy}.py
    backend/app/routers/{health,auth,recipes,taxonomy}.py
    backend/tests/{conftest,test_auth,test_recipes,test_filters}.py
    frontend/Dockerfile, frontend/Caddyfile
    frontend/site/{index.html,app.js,api.js,style.css,manifest.webmanifest,
                   sw.js,icons/}
    backup/Dockerfile, backup/backup.sh

### Tabellen (eine Migration, alle Tabellen für Phase 1–3)
| Tabelle | Spalten |
|---------|---------|
| users | id, username (unique), password_hash, created_at |
| sessions | id, user_id→users, token_hash (unique), created_at, expires_at |
| categories | id, name (unique) |
| tags | id, name (unique) |
| recipes | id, category_id→categories (null), source_kind (url/book/none), source_url, source_book, source_page, favorite, created_at, updated_at |
| recipe_versions | id, recipe_id→recipes, kind (original/own), title, intro, servings, prep_minutes, cook_minutes, created_at, updated_at; unique (recipe_id, kind) |
| ingredients | id, version_id→recipe_versions, position, amount (numeric 10,3, null), unit, name, note |
| steps | id, version_id→recipe_versions, position, text |
| recipe_tags | recipe_id, tag_id (PK beide) |
| notes | id, recipe_id, created_at, text |
| cook_log | id, recipe_id, cooked_on (date), rating 1–5, comment |
| photos | id, recipe_id, filename, is_own_result, created_at |

Löschen eines Rezepts löscht alles Zugehörige (ON DELETE CASCADE).
`original` wird nach dem Anlegen nie verändert, `own` ist bearbeitbar.
Titel liegt auf der Version (eigener Titel darf abweichen).

### Endpunkte (Präfix /api, JSON)
| Methode | Pfad | Zweck |
|---------|------|-------|
| GET | /api/health | ohne Login, `{"status":"ok"}` |
| POST | /api/auth/login | `{username,password}` → Cookie `session` (HttpOnly, Secure, SameSite=Lax, 30 Tage) |
| POST | /api/auth/logout | Sitzung löschen |
| GET | /api/auth/me | `{username}` oder 401 |
| GET | /api/recipes | Liste; Filter `q`, `category` (id), `tags` (Namen, Komma, UND), `ingredients` (Namen, Komma, UND, Teilwort, in `own`), `favorite` (true) |
| POST | /api/recipes | anlegen; Körper = RecipeInput, erzeugt `original` und `own` identisch |
| GET | /api/recipes/{id} | Rezept mit beiden Versionen, Tags, Kategorie, Quelle |
| PUT | /api/recipes/{id} | Metadaten und `own` ersetzen (Zutaten/Schritte komplett) |
| DELETE | /api/recipes/{id} | löschen |
| GET/POST | /api/categories | Liste / anlegen `{name}` |
| GET/POST | /api/tags | Liste / anlegen `{name}` |

Reserviert für Phase 2 (nicht gebaut): `/api/recipes/{id}/notes`,
`/cooklog`, `/photos`, `/api/export`, `/media/*`.

### JSON-Formen
    Ingredient  {amount: "250" | null, unit: "g", name: "Mehl", note: ""}
    Step        {text: "..."}
    Version     {title, intro, servings, prep_minutes, cook_minutes,
                 ingredients: [Ingredient], steps: [Step]}
    Source      {kind: "url"|"book"|"none", url, book, page}
    RecipeInput {category_id, tags: ["vegi"], favorite, source: Source,
                 version: Version}            # POST; PUT ersetzt own
    RecipeOut   {id, category: {id,name}|null, tags: [name], favorite,
                 source, original: Version, own: Version,
                 created_at, updated_at}
    RecipeListItem {id, title, category: {id,name}|null, tags, favorite,
                    updated_at}

### Entscheidungen
- Volltextsuche in Phase 1 mit `ILIKE` über Titel (own), Intro und
  Notizen; portabel, damit die Tests auf SQLite laufen. Ein Wechsel auf
  PostgreSQL-Volltext (`tsvector`) bleibt später möglich, der Aufruf
  bleibt `?q=`.
- Zutatenfilter: je Begriff ein EXISTS auf die Zutaten der eigenen
  Version (Teilwort, Gross/Klein egal), alle Begriffe mit UND.
- Oberfläche: eine Seite mit Hash-Routen (`#/login`, `#/`,
  `#/recipe/ID`, `#/new`, `#/edit/ID`), kein Build-Schritt.
- Caddy liefert nur HTTP auf Port `HTTP_PORT` (Vorgabe 8080) im
  internen Netz; kein Zertifikat, `auto_https off`. HTTPS und externer
  Zugriff über Nginx Proxy Manager davor (Betreiberentscheid 29.10.).
  `COOKIE_SECURE` darum Vorgabe false, einschaltbar in `.env`.
- Backup-Container: einfache Schleife (täglich), `pg_dump` plus
  tar der Fotos nach `./backups`, Aufbewahrung `BACKUP_KEEP_DAYS`
  (Default 14).

### Abschlusskriterien
Tests grün, `docker compose config` gültig, Caddyfile validiert,
Stack gestartet, Rezept über die Oberfläche angelegt.

## Phase 2 – Küche (offen)
## Phase 3 – Import (offen)
