# Rezepte-App

Private Rezeptsammlung für das Handy in der Küche.

## Container

| Container | Aufgabe |
|-----------|---------|
| `web`     | Caddy: Oberfläche, `/api` ans Backend, nur HTTP im internen Netz |
| `api`     | FastAPI: Logik, spielt beim Start die Migrationen ein |
| `db`      | PostgreSQL |
| `backup`  | Täglich Datenbank-Dump und Foto-Archiv nach `./backups`, löscht alte Dateien |

Phase 1: anmelden, Rezepte erfassen, anzeigen, bearbeiten, löschen,
filtern nach Kategorie, Tags, Zutaten und Text. Jedes Rezept hat ein
unveränderliches Original und eine eigene, bearbeitbare Version.

Später: Kochmodus, Notizen, «gekocht am» mit Bewertung, Fotos, Export
als ZIP, Import per URL.

HTTPS und Zugriff von aussen übernimmt ein vorgeschalteter Nginx Proxy
Manager (NPM); die App selbst kennt kein Zertifikat.

## Voraussetzungen

- Linux-Server mit Docker Engine 24 oder neuer und `git`.
- Für den Zugriff von aussen: NPM mit einer Domain, die auf ihn zeigt.

## Installation

```bash
git clone <URL-dieses-Repositories> rezepte-app
```

```bash
cd rezepte-app
```

```bash
cp .env.example .env
```

In `.env` `DB_PASSWORD` setzen: lang und zufällig, ohne Dollarzeichen,
z. B. aus `openssl rand -hex 24`.

```bash
docker compose up -d --build
```

Baut die Images (`--build`) und startet die Container im Hintergrund
(`-d`). Der erste Start dauert einige Minuten.

Danach ist die App im internen Netz unter `http://SERVER-IP:8080`
erreichbar (`HTTP_PORT` in `.env` ändert den Port).

## Zugriff von aussen über NPM

In NPM einen Proxy Host anlegen:

- Domain: die eigene, z. B. `rezepte.example.ch`
- Scheme `http`, Forward Hostname die Server-IP, Forward Port 8080
- SSL: Zertifikat anfordern, «Force SSL» einschalten

Dann in `.env` `COOKIE_SECURE=true` setzen und ausführen:

```bash
docker compose up -d api
```

Startet `api` mit der neuen Einstellung; das Anmelde-Cookie geht nur
noch über HTTPS, die Anmeldung intern über `http://` geht nicht mehr.

## Benutzer anlegen

```bash
docker compose exec api python -m app.cli create-user NAME
```

Führt den Befehl im laufenden `api`-Container aus und fragt nach dem
Passwort.

Passwort ändern:

```bash
docker compose exec api python -m app.cli set-password NAME
```

Alle Anmeldungen auf allen Geräten beenden (z. B. Handy verloren):

```bash
docker compose exec api python -m app.cli purge-sessions
```

## Als App auf dem Handy

Die NPM-Adresse öffnen, anmelden (gilt `SESSION_DAYS` Tage, Vorgabe
30), dann auf den Startbildschirm legen (braucht HTTPS, intern über
`http://` bleibt es ein Browser-Lesezeichen):

- **iPhone (Safari):** Teilen-Symbol, «Zum Home-Bildschirm».
- **Android (Chrome):** Menü, «App installieren».

## Alltagsbefehle

Alle Befehle im Ordner `rezepte-app` ausführen.

```bash
docker compose ps
```

Zustand der Container (`running`, `healthy`).

```bash
docker compose logs -f
```

Logs aller Container live, beenden mit Ctrl+C. Mit Namen dahinter nur
einer: `docker compose logs -f api`.

```bash
git pull && docker compose up -d --build
```

Update: holt den Code und baut nur die geänderten Container neu.
Datenbank und Fotos bleiben, Migrationen laufen beim Start.

```bash
docker compose down
```

Stoppt und entfernt die Container; Volumes (Datenbank, Fotos)
bleiben. Nie `docker compose down -v`: löscht die Volumes.

```bash
docker compose up -d
```

Startet wieder. Mit Containername dahinter nur diesen, z. B. nach einer
Änderung in `.env`: `docker compose up -d api`.

## Backup

Der Container `backup` schreibt täglich um `BACKUP_HOUR` Uhr (Vorgabe 3,
Zeitzone `TZ`) nach `./backups`:

- `db-JJJJMMTT-HHMMSS.dump`: Datenbank (`pg_dump`, komprimiert)
- `media-JJJJMMTT-HHMMSS.tar.gz`: Fotos (erst wenn welche da sind)

Dateien älter als `BACKUP_KEEP_DAYS` Tage (Vorgabe 14) werden gelöscht.
Log: `docker compose logs backup`.

`./backups` liegt auf demselben Server. Regelmässig woanders hin
kopieren, z. B. vom eigenen Rechner:

```bash
rsync -av BENUTZER@SERVER:rezepte-app/backups/ ./rezepte-backups/
```

Backup sofort:

```bash
docker compose run --rm backup now
```

Startet einen einmaligen `backup`-Container, der nach dem Backup wieder
entfernt wird (`--rm`).

## Wiederherstellen

Der Stack läuft, die Dateien liegen in `./backups`. `DATUM` steht für
den Zeitstempel im Dateinamen, z. B. `20261029-030000`.

```bash
docker compose stop api
```

Hält `api` an, damit niemand in die Datenbank schreibt.

```bash
docker compose exec -T db pg_restore -U rezepte -d rezepte --clean --if-exists --no-owner < backups/db-DATUM.dump
```

Spielt den Dump im `db`-Container ein (`-T`: Eingabe von der Konsole,
`--clean`: vorhandene Tabellen vorher löschen). Meldungen über nicht
vorhandene Objekte sind normal.

Nur wenn ein `media-`Archiv vorhanden ist:

```bash
docker compose run --rm --entrypoint tar -v "$PWD/backups:/backups" api -xzf /backups/media-DATUM.tar.gz -C /data
```

Entpackt das Archiv in das Foto-Volume (`--entrypoint tar` ersetzt den
normalen Start der API).

```bash
docker compose up -d
```

Startet `api` wieder; ein Dump einer älteren Version wird durch die
Migrationen aktualisiert.

## Umzug auf einen anderen Server

1. Alter Server: `docker compose run --rm backup now`.
2. `.env` und `backups/` sichern (`scp` oder `rsync`).
3. Neuer Server: Installation wie oben, `.env` hinüberkopieren.
4. `backups/` nach `rezepte-app/` kopieren, «Wiederherstellen»
   ausführen.
5. In NPM den Proxy Host auf die neue Server-IP zeigen lassen, dann
   den alten Server mit `docker compose down` stoppen.

## Entwicklung

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

Stack im Vordergrund: `backend/app` und `frontend/site` sind
eingebunden (Änderungen wirken ohne Neubau, die API lädt neu), die
Datenbank ist auf `localhost:5432` erreichbar, API-Doku unter
`http://localhost:8080/api/docs`.

Backend-Tests ohne Docker (Python 3.12):

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt && .venv/bin/pytest
```

Richtet die virtuelle Umgebung ein und führt die Tests aus; später
genügt `cd backend && .venv/bin/pytest`.

## Fehlersuche

**Intern erreichbar, über NPM nicht:** Im Proxy Host Scheme `http`,
Server-IP und Port 8080 prüfen; `docker compose logs web` zeigt, ob
Anfragen ankommen.

**Anmeldung geht intern nicht mehr:** `COOKIE_SECURE=true` ist gesetzt;
dann nur über die NPM-Adresse anmelden.

**Container startet nicht:** `docker compose ps` zeigt `restarting`
oder `exited`; dann `docker compose logs api` (oder der betroffene
Name).

**«DB_PASSWORD fehlt in .env»:** `.env` fehlt oder der Wert ist leer.

**Passwort vergessen:**
`docker compose exec api python -m app.cli set-password NAME`.

**Datenbank-Passwort ändern:** PostgreSQL hat es im Volume gespeichert.
Zuerst in der Datenbank ändern:
`docker compose exec db psql -U rezepte -c "ALTER USER rezepte PASSWORD 'NEU';"`,
dann `.env` anpassen und `docker compose up -d`.
