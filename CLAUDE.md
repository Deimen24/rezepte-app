# Rezepte-App – Arbeitsregeln für Claude

Diese Datei gilt für jede Sitzung in diesem Repository. Der vollständige
Projektauftrag steht in `docs/AUFTRAG.md`, der Stand je Phase in
`docs/PLAN.md`.

## Kontext
Rezeptsammlung für eine Person, Handy in der Küche. Der Betreiber
arbeitet ca. 1 Stunde pro Woche daran und hat wenig Docker-Erfahrung.

## Technologie (fest vorgegeben)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2
- Datenbank: PostgreSQL
- Oberfläche: PWA, erste Version HTML/CSS/JS ohne Framework
- Webserver: Caddy, nur HTTP. HTTPS über Nginx Proxy Manager (NPM)
  ausserhalb des Repos.
- Betrieb: Docker Compose, selbst gehostet, keine Cloud-Dienste

## Regeln
- Vier Container in `compose.yaml`: web (Caddy), api (FastAPI), db
  (PostgreSQL), backup (pg_dump + Fotos nach ./backups).
- `.env` hat genau einen Pflichtwert: `DB_PASSWORD`.
- Inbetriebnahme: git clone, .env ausfüllen, `docker compose up -d --build`.
- `compose.dev.yaml` für Entwicklung (Mounts, Auto-Reload, DB-Port,
  API-Doku unter /api/docs).
- Dateizugriff auf Fotos nur in `backend/app/storage.py`.
- Geschäftslogik in `backend/app/services/`, Router dünn.
- Jede Datenmodell-Änderung als Alembic-Migration, nie `create_all`.
- Keine Abhängigkeiten ohne gepinnte Version, keine Alpha-Versionen.
- Alle Endpunkte ausser Login, Ersteinrichtung, Health und
  Teilen-Links erfordern Login. Der Benutzer entsteht beim ersten
  Öffnen im Browser, nicht per CLI.

## Sprache
- Code, Kommentare, Commit-Texte: Englisch.
- README, Oberfläche, Antworten an den Betreiber: Deutsch, Schweizer
  Schreibweise («ss» statt «ß»).
- Keine Floskeln, nichts Offensichtliches, keine Wiederholungen, keine
  Begründungen des Selbstverständlichen: README, .env.example,
  Kommentare, Oberfläche, Antworten. Vor jedem Commit alle Texte
  darauf prüfen.

## Codestil
Linux-Kernel-Stil, soweit die Sprache es erlaubt: Tabs mit 8 Zeichen,
max. 80 Spalten, K&R-Klammern, kurze Funktionen mit einer Aufgabe,
Konstanten in GROSSBUCHSTABEN, kurze lokale Namen, beschreibende
Funktionsnamen, kein camelCase, Mehrzeilenkommentare mit /* */ und
Sternchen-Spalte. Ausnahmen: YAML braucht Leerzeichen, Python-Klassen
bleiben PascalCase. Python wird mit Tabs eingerückt.

## Arbeitsweise
- Phase für Phase. Jede Phase beginnt mit einem kurzen Plan (Dateien,
  Endpunkte, Tabellen) und wartet auf das OK des Betreibers.
- Kleine, nachvollziehbare Commits mit klaren Meldungen.
- Tests mit pytest. Vor jedem Phasen-Abschluss: Tests grün,
  `docker compose config` gültig, Caddyfile validiert, Stack lokal
  gestartet.
- Docker-Befehle für den Betreiber immer mit einem Satz erklären.
- Bei Unklarheit oder zwei guten Lösungen kurz nachfragen statt raten.
  Entscheidungen, die einen späteren Wechsel von Hosting oder
  Oberfläche erschweren, immer ansprechen.
- Branch: `claude/admiring-archimedes-96h6mx`.
