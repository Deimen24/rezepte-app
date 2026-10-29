# Plan und Stand

## Phase 1 – Fundament (gebaut, Stack-Start auf dem Server offen)

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
- Volltextsuche mit `ILIKE` über Titel (own), Intro und Notizen, damit
  die Tests auf SQLite laufen; `tsvector` später hinter demselben `?q=`.
- Zutatenfilter: je Begriff ein EXISTS auf die Zutaten der eigenen
  Version (Teilwort, Gross/Klein egal), alle Begriffe mit UND.
- Oberfläche: eine Seite mit Hash-Routen (`#/login`, `#/`,
  `#/recipe/ID`, `#/new`, `#/edit/ID`), kein Build-Schritt.
- Caddy nur HTTP auf `HTTP_PORT` (8080), `auto_https off`; HTTPS über
  NPM (Entscheid 29.10.). `COOKIE_SECURE` darum Vorgabe false.
- Backup: Schleife, täglich `pg_dump` und tar nach `./backups`,
  Aufbewahrung `BACKUP_KEEP_DAYS` (14).

### Abschlusskriterien
Tests grün, `docker compose config` gültig, Caddyfile validiert,
Stack gestartet, Rezept über die Oberfläche angelegt.

## Phase 2 – Küche (Plan, wartet auf OK)

### Dateien
    backend/requirements.txt: + pillow
    backend/app/images.py                  resize, EXIF-Drehung, JPEG
    backend/app/services/{notes,cooklog,photos,export}.py
    backend/app/routers/{notes,cooklog,photos,export,media}.py
    backend/app/schemas.py                 NoteIn/Out, CookLogIn/Out,
                                           PhotoOut, RecipeOut erweitert
    backend/tests/test_{notes,cooklog,photos,export,images}.py
    frontend/site/cook.js                  Kochmodus
    frontend/site/app.js, api.js, style.css, sw.js (CACHE_VERSION)
    frontend/Caddyfile                     request_body max_size 20MB

### Tabellen
Keine neue Migration: `notes`, `cook_log`, `photos` sind seit 0001 da.

### Endpunkte (alle mit Login)
| Methode | Pfad | Zweck |
|---------|------|-------|
| POST | /api/recipes/{id}/notes | `{text}` → NoteOut |
| DELETE | /api/recipes/{id}/notes/{nid} | 204 |
| POST | /api/recipes/{id}/cooklog | `{cooked_on, rating 1–5, comment}` → CookLogOut |
| DELETE | /api/recipes/{id}/cooklog/{cid} | 204 |
| PUT | /api/recipes/{id}/favorite | `{favorite}` → `{favorite}` |
| POST | /api/recipes/{id}/photos | multipart `file`, `is_own_result` → PhotoOut |
| DELETE | /api/recipes/{id}/photos/{pid} | 204, löscht Dateien |
| GET | /media/{name} | Bilddatei aus storage.py |
| GET | /api/export | ZIP: `recipes.json` (alle Rezepte mit beiden Versionen, Notizen, Kochlog, Fotoliste) und `photos/` |

### JSON-Formen
    NoteOut     {id, created_at, text}
    CookLogOut  {id, cooked_on, rating, comment}
    PhotoOut    {id, url, thumb_url, is_own_result, created_at}
    RecipeOut   + notes: [NoteOut], cook_log: [CookLogOut],
                  photos: [PhotoOut]
    RecipeListItem + thumb_url | null, cooked_count, last_cooked | null

### Fotos
- Upload bis 20 MB, Formate JPEG, PNG, HEIC nicht (iPhone liefert bei
  `accept="image/*"` JPEG).
- Serverseitig: EXIF-Drehung anwenden, längste Seite 1600 px, JPEG
  Qualität 85, EXIF entfernt; Vorschau 400 px. Dateinamen
  `{photo_id}.jpg` und `{photo_id}_t.jpg`, nur über `storage.py`.
- Löschen eines Rezepts löscht die Dateien mit.

### Oberfläche
- Detail: Favorit-Stern (ein Tipp), Notiz-Feld mit «Speichern»,
  «Gekocht» mit Datum (heute), Sterne 1–5, Kommentar; Fotoliste,
  Upload über Kamera oder Galerie (`capture="environment"`), Markierung
  «eigenes Ergebnis»; Knopf «Kochen».
- Kochmodus `#/cook/ID`: Wake Lock (`navigator.wakeLock`), Schrift
  grösser, Zutaten zum Abhaken, ein Schritt gross mit «Weiter» und
  «Zurück», Abhak-Stand in `sessionStorage`. Beim Verlassen «Gekocht»
  anbieten.
- Liste: Vorschaubild, Export-Knopf lädt `/api/export`.

### Tests
Service und API je Endpunkt, Bildverkleinerung (Grösse, Drehung, kein
EXIF), Export-ZIP (Inhalt, Fotos dabei), Löschen räumt Dateien weg,
Fehlerfälle (fremde Rezept-ID, zu grosse Datei, kein Bild).

## Phase 3 – Import (offen)
