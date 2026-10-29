# Rezepte-App – Projektauftrag

## Kontext
Private Rezeptsammlung für eine Person, bedient hauptsächlich auf dem
Handy (iPhone und Android) in der Küche. Ich bin kein Profi-Entwickler,
arbeite ca. 1 Stunde pro Woche daran und habe wenig Docker-Erfahrung.
Du baust eine solide, professionelle Lösung, keine Einsteigervariante.

## Problem, das gelöst wird
Ich finde Rezepte online oder in Büchern, koche nach, passe sie an und
finde später weder Rezept noch Quelle noch meine Anpassungen wieder.

## Technologie (fest vorgegeben)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2
- Datenbank: PostgreSQL (relational, wegen Zutatenfiltern)
- Oberfläche: Progressive Web App (installierbar ohne App Store).
  Erste Version bewusst einfach (HTML/CSS/JS ohne Framework), später
  durch eine Framework-Oberfläche ersetzbar.
- Webserver/HTTPS: Caddy (automatische Zertifikate von Let's Encrypt)
- Betrieb: Docker Compose, selbst gehostet. Kein AWS, keine
  Cloud-Spezialdienste.

## Architektur: vier Container in einer compose.yaml
| Container | Aufgabe |
|-----------|---------|
| web   | Caddy: Oberfläche ausliefern, /api und /media ans Backend weiterleiten, HTTPS |
| api   | FastAPI: gesamte Logik. Spielt beim Start `alembic upgrade head` selbst ein |
| db    | PostgreSQL mit Volume |
| backup| Täglich pg_dump + Foto-Archiv nach ./backups, alte Backups nach N Tagen löschen |

Regeln:
- Alles wird aus dem Repository gebaut. Kein manueller Download, keine
  Konfiguration von Hand ausserhalb der Datei .env.
- .env hat genau zwei Pflichtwerte: DOMAIN und DB_PASSWORD. Alles
  andere hat sinnvolle Defaults. .env.example mit Erklärung liegt bei.
- Inbetriebnahme muss mit drei Schritten funktionieren:
  git clone, .env ausfüllen, docker compose up -d --build.
- Zusätzlich compose.dev.yaml für die Entwicklung: Code-Mounts,
  Auto-Reload, DB-Port auf localhost, API-Doku unter /api/docs.
- Fotos liegen in einem Docker-Volume. Der Dateizugriff ist in einem
  einzigen Modul gekapselt (storage.py), damit später S3 möglich ist.
- Login: ein Benutzer, Passwort mit Argon2 gehasht, Sitzung als
  zufälliger Token in HttpOnly-Cookie, Token-Hash in der DB.
  Benutzer wird per CLI-Befehl im Container angelegt.
- Geschäftslogik liegt in app/services/, unabhängig von HTTP.
  Router in app/routers/ sind dünn. Grund: Oberfläche und Hosting
  sollen austauschbar bleiben, und ein zweites Projekt (zeitgesteuerte
  Erinnerungen) soll später als weiterer Container dazukommen.

## Repository-Struktur
    compose.yaml, compose.dev.yaml, .env.example, README.md, CLAUDE.md
    backend/ Dockerfile, requirements.txt (Versionen gepinnt), entrypoint.sh
    app/ main.py config.py db.py models.py auth.py storage.py cli.py
    app/services/ app/routers/ migrations/ (Alembic)
    frontend/ Dockerfile, Caddyfile, site/
    backup/ backup.sh

## Datenmodell
- Jedes Rezept hat genau zwei Versionen: `original` (unverändert, wie
  importiert oder erfasst) und `own` (meine bearbeitbare Version,
  startet als Kopie). Das Original wird nie verändert.
- Quelle pro Rezept: URL, oder Buch und Seite, oder keine.
- Zutaten strukturiert: Menge (Dezimal), Einheit, Name, Bemerkung,
  Reihenfolge. Zutaten und Schritte gehören zur Version.
- Zum Rezept gehören: Kategorie (eine), Tags (mehrere), datierte
  Notizen, Einträge «gekocht am» mit Bewertung 1–5 und Kommentar,
  Favorit-Flag, Fotos (mit Kennzeichnung «eigenes Ergebnisfoto»).
- Volltextsuche über Titel und Notizen. Zutatenfilter mit mehreren
  Zutaten als UND («Kürbis und Feta»), sucht in der eigenen Version.

## Funktionen nach Phasen
Jede Phase endet mit einem lauffähigen Stand, den ich per
`docker compose up -d --build` starten und auf dem Handy nutzen kann.

**Phase 1 – Fundament**
Compose-Setup mit allen vier Containern, Datenmodell, Migration,
Login, CLI für Benutzer, Rezepte erfassen/anzeigen/bearbeiten/löschen,
Filter (Kategorie, Tags, Zutaten, Volltext), einfache PWA-Oberfläche
mit grossen Schaltflächen, README für Betrieb.

**Phase 2 – Küche**
Kochmodus (Bildschirm bleibt an via Wake Lock API, grosse Schrift,
Zutaten abhaken, aktueller Schritt hervorgehoben), Notizen schnell
erfassen, «gekocht am» mit Bewertung, Favoriten, Fotos hochladen
(serverseitig verkleinern), Export aller Rezepte als ZIP (JSON + Fotos).

**Phase 3 – Import**
Rezept per URL importieren: zuerst schema.org/Recipe (JSON-LD) lesen,
Fallback mit Heuristik. Zutaten-Text in Menge/Einheit/Name zerlegen.
Immer Vorschau mit Korrekturmöglichkeit vor dem Speichern. Original
und Quelle werden gespeichert.

**Spätere Phasen (nur Architektur dafür offenhalten, nicht bauen):**
Timer aus Zeitangaben in Schritten, Speichern aus dem Handy-Browser
(Share Target auf Android, Kurzbefehl auf iOS), Portionen umrechnen,
Einkaufsliste nach Microsoft To Do (ohne Duplikate, Vorräte wie Salz
und Öl ausgenommen), Kochbuchseiten per Foto erfassen (OCR/KI),
Teilen einzelner Rezepte (nur eigene Version, keine Originaltexte),
Nährwerte pro Portion.

## Bewusst nicht gebaut
Vorratsverwaltung mit Ablaufdaten, Community, Blog-Feeds, Sortierung
der Einkaufsliste nach Ladenabteilung, Mehrbenutzer-Verwaltung.

## Nicht-funktionale Anforderungen
- Gut bedienbar in der Küche: grosse Schaltflächen, schnell, wenig Tippen.
- Hell- und Dunkelmodus. Funktioniert auf iPhone-Safari und Android-Chrome.
- HTTPS immer. Alle Endpunkte ausser Login und Health erfordern Login.
- Backup ohne eigenen Aufwand; Wiederherstellung im README beschrieben.
- Kosten: nur Server und Domain.

## Codestil
Linux-Kernel-Stil, soweit die Sprache es erlaubt: Tabs mit 8 Zeichen,
max. 80 Spalten, K&R-Klammern, kurze Funktionen mit einer Aufgabe,
Konstanten in GROSSBUCHSTABEN, kurze lokale Namen, beschreibende
Funktionsnamen, kein camelCase, Mehrzeilenkommentare mit /* */ und
Sternchen-Spalte. Ausnahmen: YAML braucht Leerzeichen, Python-Klassen
bleiben PascalCase. Kommentare im Code auf Englisch, README und
Oberfläche auf Deutsch (Schweizer Schreibweise, «ss» statt «ß»).

## Arbeitsweise
- Arbeite Phase für Phase. Beginne jede Phase mit einem kurzen Plan
  (Dateien, Endpunkte, Tabellen) und warte auf mein OK.
- Kleine, nachvollziehbare Commits mit klaren Meldungen.
- Jede Datenmodell-Änderung als Alembic-Migration, nie create_all.
- Tests für Services und API (pytest, SQLite oder Test-Postgres).
  Vor jedem Phasen-Abschluss: Tests grün, compose config gültig,
  Caddyfile validiert, Compose-Stack lokal mit DOMAIN=localhost gestartet.
- Keine Abhängigkeiten ohne gepinnte Version. Keine Alpha-Versionen.
- Erkläre mir Docker-Befehle, die ich selbst ausführen muss, immer mit
  einem Satz, was sie tun. Ich lerne Docker nebenbei.
- Wenn eine Anforderung unklar ist oder zwei gute Lösungen existieren,
  frag mich kurz, statt zu raten. Entscheidungen, die den späteren
  Wechsel von Hosting oder Oberfläche erschweren würden, immer
  ansprechen.
- README muss für jemanden mit wenig Docker-Wissen ausreichen:
  Installation, Handy-Zugriff (Domain, Ports 80/443), Alltagsbefehle,
  Backup wiederherstellen, Umzug auf anderen Server.
