# Rezepte-App

Rezeptsammlung für das Handy in der Küche.

| Container | Aufgabe |
|-----------|---------|
| `web`     | Caddy, HTTP auf Port 8080 |
| `api`     | FastAPI, Migrationen beim Start |
| `db`      | PostgreSQL |
| `backup`  | Täglich DB-Dump und Foto-Archiv nach `./backups` |

HTTPS: Nginx Proxy Manager (NPM) davor.

Phase 1: Rezepte erfassen, bearbeiten, löschen; Filter nach Kategorie,
Tags, Zutaten, Text; Original und eigene Version je Rezept.
Später: Kochmodus, Notizen, «gekocht am», Fotos, Export, Import per URL.

## Installation

Server mit Docker Engine 24+ und `git`.

```bash
git clone <URL-dieses-Repositories> rezepte-app
```

```bash
cd rezepte-app
```

```bash
cp .env.example .env
```

`DB_PASSWORD` in `.env` setzen (`openssl rand -hex 24`, kein `$`).

```bash
docker compose up -d --build
```

Baut die Images und startet im Hintergrund. App: `http://SERVER-IP:8080`
(`HTTP_PORT` in `.env`).

## NPM

Proxy Host: Scheme `http`, Server-IP, Port 8080, SSL mit «Force SSL».

Dann `COOKIE_SECURE=true` in `.env`:

```bash
docker compose up -d api
```

Startet `api` neu. Anmeldung danach nur noch über HTTPS.

## Benutzer

```bash
docker compose exec api python -m app.cli create-user NAME
```

Fragt das Passwort ab.

```bash
docker compose exec api python -m app.cli set-password NAME
```

```bash
docker compose exec api python -m app.cli purge-sessions
```

Meldet alle Geräte ab.

## Handy

Anmeldung gilt `SESSION_DAYS` Tage (30). Startbildschirm nur über HTTPS:

- iPhone, Safari: Teilen, «Zum Home-Bildschirm»
- Android, Chrome: Menü, «App installieren»

## Betrieb

Im Ordner `rezepte-app`:

```bash
docker compose ps
```

```bash
docker compose logs -f api
```

Logs von `api`; ohne Namen alle. Ctrl+C beendet.

```bash
git pull && docker compose up -d --build
```

Update; Daten bleiben, Migrationen laufen beim Start.

```bash
docker compose down
```

Stoppt. Nie `down -v`: löscht Datenbank und Fotos.

```bash
docker compose up -d
```

Startet; mit Name dahinter nur diesen Container.

## Backup

Täglich um `BACKUP_HOUR` Uhr (3, Zeitzone `TZ`) nach `./backups`:
`db-JJJJMMTT-HHMMSS.dump` und `media-JJJJMMTT-HHMMSS.tar.gz`. Löscht
Dateien älter als `BACKUP_KEEP_DAYS` Tage (14).

`./backups` regelmässig auf einen anderen Rechner kopieren:

```bash
rsync -av BENUTZER@SERVER:rezepte-app/backups/ ./rezepte-backups/
```

Sofort:

```bash
docker compose run --rm backup now
```

## Wiederherstellen

`DATUM` = Zeitstempel im Dateinamen, z. B. `20261029-030000`.

```bash
docker compose stop api
```

```bash
docker compose exec -T db pg_restore -U rezepte -d rezepte --clean --if-exists --no-owner < backups/db-DATUM.dump
```

Meldungen über nicht vorhandene Objekte sind normal.

```bash
docker compose run --rm --entrypoint tar -v "$PWD/backups:/backups" api -xzf /backups/media-DATUM.tar.gz -C /data
```

Entpackt die Fotos ins Volume.

```bash
docker compose up -d
```

## Umzug

1. Alt: `docker compose run --rm backup now`
2. `.env` und `backups/` kopieren
3. Neu: Installation, `.env` einsetzen, Wiederherstellen
4. NPM auf neue IP, alt `docker compose down`

## Entwicklung

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

Code eingebunden, Auto-Reload, DB auf `localhost:5432`, API-Doku unter
`http://localhost:8080/api/docs`.

Tests:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt && .venv/bin/pytest
```

## Fehlersuche

- Intern ja, NPM nein: Proxy Host prüfen (`http`, IP, 8080);
  `docker compose logs web`.
- Anmeldung intern geht nicht: `COOKIE_SECURE=true`, nur über HTTPS.
- Container `restarting`/`exited`: `docker compose logs NAME`.
- Passwort vergessen: `set-password`.
- DB-Passwort ändern: zuerst in der DB,
  `docker compose exec db psql -U rezepte -c "ALTER USER rezepte PASSWORD 'NEU';"`,
  dann `.env`, dann `docker compose up -d`.
