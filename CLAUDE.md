# Rezepte-App – Arbeitsregeln für Claude

Diese Datei gilt für jede Sitzung in diesem Repository. Der vollständige
Projektauftrag steht in `docs/AUFTRAG.md`, der Stand je Phase in
`docs/PLAN.md`.

## Kontext
Private Rezeptsammlung für eine Person, bedient hauptsächlich auf dem
Handy (iPhone und Android) in der Küche. Der Betreiber ist kein
Profi-Entwickler, arbeitet ca. 1 Stunde pro Woche daran und hat wenig
Docker-Erfahrung. Ziel ist eine solide, professionelle Lösung.

## Technologie (fest vorgegeben)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2
- Datenbank: PostgreSQL
- Oberfläche: PWA, erste Version HTML/CSS/JS ohne Framework
- Webserver/HTTPS: Caddy (Let's Encrypt)
- Betrieb: Docker Compose, selbst gehostet, keine Cloud-Dienste

## Regeln
- Vier Container in `compose.yaml`: web (Caddy), api (FastAPI), db
  (PostgreSQL), backup (pg_dump + Fotos nach ./backups).
- `.env` hat genau zwei Pflichtwerte: `DOMAIN` und `DB_PASSWORD`.
- Inbetriebnahme: git clone, .env ausfüllen, `docker compose up -d --build`.
- `compose.dev.yaml` für Entwicklung (Mounts, Auto-Reload, DB-Port,
  API-Doku unter /api/docs).
- Dateizugriff auf Fotos nur in `backend/app/storage.py`.
- Geschäftslogik in `backend/app/services/`, Router dünn.
- Jede Datenmodell-Änderung als Alembic-Migration, nie `create_all`.
- Keine Abhängigkeiten ohne gepinnte Version, keine Alpha-Versionen.
- Alle Endpunkte ausser Login und Health erfordern Login.

## Sprache
- Code, Kommentare, Commit-Texte: Englisch.
- README, Oberfläche, Antworten an den Betreiber: Deutsch, Schweizer
  Schreibweise («ss» statt «ß»).

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
  `docker compose config` gültig, Caddyfile validiert, Stack lokal mit
  `DOMAIN=localhost` gestartet.
- Docker-Befehle für den Betreiber immer mit einem Satz erklären.
- Bei Unklarheit oder zwei guten Lösungen kurz nachfragen statt raten.
  Entscheidungen, die einen späteren Wechsel von Hosting oder
  Oberfläche erschweren, immer ansprechen.
- Branch: `claude/admiring-archimedes-96h6mx`.
