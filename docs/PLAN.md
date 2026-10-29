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

## Phase 2 – Küche (gebaut, Stack-Start auf dem Server offen)

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

### Stand 29.10.
- Backend und Frontend gebaut; 318 Tests grün; Caddyfile validiert.
- Oberfläche in Playwright geprüft: Favorit, Fotos (Upload, Overlay,
  Löschen), Notizen, Kochlog, Kochmodus (Wake Lock, Abhaken, Schritte,
  Stand nach Reload), Export-Link.
- Offen: Stack-Start beim Betreiber, Foto-Upload vom echten iPhone.

## Phase 3 – Import (Plan, wartet auf OK)

### Dateien
    backend/requirements.txt: + httpx, beautifulsoup4
    backend/app/importer/fetch.py        URL laden mit Schutz
    backend/app/importer/jsonld.py       schema.org/Recipe
    backend/app/importer/heuristic.py    Fallback aus HTML
    backend/app/importer/ingredients.py  Zutatenzeile zerlegen
    backend/app/importer/duration.py     ISO 8601 (PT1H30M) → Minuten
    backend/app/services/importer.py     Ablauf: laden, parsen, Vorschau
    backend/app/services/photos.py       + add_photo_from_url
    backend/app/routers/importer.py
    backend/app/schemas.py               ImportIn, ImportPreview,
                                         IngredientLinesIn, PhotoUrlIn
    backend/tests/fixtures/*.html, *.json
    backend/tests/test_{jsonld,heuristic,ingredients,duration,fetch,
                        import_api}.py
    frontend/site/import.js              Ansicht #/import
    frontend/site/app.js, api.js, style.css, sw.js, manifest

### Tabellen
Keine neue Migration. Quelle landet in `recipes.source_*`, Original in
`recipe_versions` (kind original), wie bisher.

### Endpunkte (mit Login)
| Methode | Pfad | Zweck |
|---------|------|-------|
| POST | /api/import/fetch | `{url}` → ImportPreview, speichert nichts |
| POST | /api/import/ingredients | `{lines: [str]}` → `[IngredientIn + raw]`, für eingefügten Text (Buch) und Nachbearbeitung |
| POST | /api/recipes/{id}/photos/url | `{url}` → PhotoOut, lädt das Rezeptbild nach dem Speichern |

Speichern läuft über das bestehende `POST /api/recipes` mit
`source.kind = "url"`.

### JSON-Formen
    ImportPreview {source: Source, version: VersionIn-Form mit
                   ingredients: [{amount, unit, name, note, raw}],
                   image_url | null, method: "jsonld" | "heuristic",
                   warnings: [str]}

### Laden (fetch.py)
- Nur http/https, max. 5 Weiterleitungen, 10 s, 5 MB, nur `text/html`.
- Ziel-IP aufgelöst und geprüft: keine privaten, Loopback-, Link-Local-
  oder Metadaten-Adressen (SSRF). Fehler → 422 mit Grund.
- Eigener User-Agent; kein JavaScript-Rendering.

### JSON-LD (jsonld.py)
- Alle `<script type="application/ld+json">`, auch `@graph` und
  Listen; `@type` "Recipe" als String oder in Liste.
- Felder: name, description, recipeYield (Zahl aus «4 Portionen»),
  prepTime/cookTime/totalTime (ISO 8601), recipeIngredient,
  recipeInstructions (String, Liste von Strings, HowToStep,
  HowToSection mit itemListElement), image (String, Liste, ImageObject).
- HTML-Entities und Tags im Text entfernt.

### Heuristik (heuristic.py)
- Titel: og:title, sonst `<h1>`, sonst `<title>`.
- Zutaten: erste `<ul>`/`<ol>` nach einer Überschrift mit «Zutaten»,
  «Ingredients»; sonst die Liste mit den meisten Zeilen, die mit einer
  Zahl beginnen.
- Schritte: `<ol>` nach «Zubereitung», «Anleitung», «Instructions»,
  «Method»; sonst Absätze nach dieser Überschrift bis zur nächsten.
- Jede Unsicherheit als Eintrag in `warnings` («Schritte geraten»).

### Zutatenzeile (ingredients.py)
- Menge: `250`, `1.5`, `1,5`, `1/2`, `½`, `1 ½`, Bereich `2-3` → 2 mit
  Hinweis «2–3» in note.
- Einheiten DE/EN mit Normalisierung: g, kg, ml, dl, l, EL, TL, Prise,
  Stück, Bund, Zehe(n), Dose, Pck., Tasse, cup(s), tbsp, tsp, oz, lb.
- Rest = Name; Klammern und Text nach dem ersten Komma → note.
- `raw` bleibt immer erhalten, Original-Version übernimmt `raw` als
  Name, wenn der Parser nichts zerlegen kann.

### Oberfläche
- `#/import` (Knopf «Import» neben «+ Neu»): URL-Feld, «Laden»;
  Vorschau = das bestehende Formular, vorbefüllt, darüber Zeile mit
  Methode und Warnungen, Bild mit Häkchen «Bild übernehmen»;
  «Speichern» → POST /api/recipes, dann Bild nach `photos/url`.
- `#/import?url=…` befüllt das Feld und lädt sofort (Vorbereitung für
  Share Target und iOS-Kurzbefehl, beide noch nicht gebaut).
- Im Formular (neu/bearbeiten): «Zutaten einfügen» öffnet ein
  Textfeld; Zeilen gehen an `/api/import/ingredients` und werden zu
  Zutatenzeilen (für Buchrezepte).

### Tests
- jsonld: Fixtures mit einfachem Recipe, `@graph`, Typ-Liste,
  HowToSection, ImageObject, recipeYield als Text, Entities.
- heuristic: zwei HTML-Fixtures (Überschriften DE/EN) und eine ohne
  Überschriften; Warnungen vorhanden.
- ingredients: Tabelle mit rund 40 Zeilen DE/EN, Brüche, Bereiche,
  ohne Menge, Klammern.
- duration: PT30M, PT1H30M, P0DT2H, ungültig → None.
- fetch: httpx MockTransport für Weiterleitung, zu gross, falscher
  Typ, Timeout; private Adressen abgelehnt (DNS gemockt).
- API: Vorschau speichert nichts (Rezeptanzahl gleich), 401, 422 bei
  ungültiger URL; photos/url legt Foto an; Speichern aus Vorschau
  ergibt Original = Vorschau.


