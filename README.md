# Rezepte-App

Rezeptsammlung für das Handy in der Küche.

| Container | Aufgabe |
|-----------|---------|
| `web`     | Caddy, HTTP auf Port 8080 |
| `api`     | FastAPI, Migrationen beim Start |
| `db`      | PostgreSQL |
| `backup`  | Täglich DB-Dump und Foto-Archiv nach `./backups` |

HTTPS: Nginx Proxy Manager (NPM) davor.

Rezepte erfassen, bearbeiten, löschen; Filter nach Kategorie, Tags,
Zutaten, Text; Original und eigene Version je Rezept; Kochmodus
(Bildschirm bleibt an); Notizen; «gekocht am» mit Sternen; Fotos; Export
als ZIP (Menü «⋯»); Import per URL (schema.org, sonst geraten) mit
Vorschau; Zutaten als Text einfügen; Portionen umrechnen; Timer in
Schritten; Nährwerte; Einkaufsliste mit Vorräten, nach Microsoft To Do;
Teilen per Link; Buchseite per Foto; Teilen aus dem Handy-Browser.

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

## Aus dem Handy-Browser speichern

Android, App installiert (siehe «Handy»): Teilen, «Rezepte».

iPhone, App «Kurzbefehle»:

1. «+», Name «Rezept speichern».
2. «i», «Im Teilen-Menü anzeigen» ein, Eingabetyp nur «URLs».
3. Aktion «URL codieren» mit «Kurzbefehl-Eingabe».
4. Aktion «URL öffnen»: `https://DOMAIN/#/import?url=`, dahinter das
   Ergebnis von Schritt 3.
5. Safari: Teilen, «Rezept speichern».

## Microsoft To Do

Einmal im [Entra admin center](https://entra.microsoft.com):

1. «App registrations», «New registration».
2. Kontotyp: persönliche Konten und Konten jeder Organisation.
3. Plattform «Mobile and desktop applications»; Redirect leer lassen,
   sonst `https://login.microsoftonline.com/common/oauth2/nativeclient`.
4. «Authentication», «Allow public client flows»: Yes.
5. «API permissions», «Microsoft Graph», «Delegated», `Tasks.ReadWrite`.

Kein Client Secret. «Application (client) ID» als `MS_CLIENT_ID` in
`.env`:

```bash
docker compose up -d api
```

```bash
docker compose exec api python -m app.cli todo-login
```

Zeigt Adresse und Code für die Anmeldung im Browser.

Die Einkaufsliste legt offene Einträge in der To-Do-Liste `TODO_LIST`
(`Einkauf`) an, vorhandene Titel nicht nochmals. Zutaten unter
`#/pantry` (Salz, Öl, …) kommen nicht auf die Einkaufsliste.

## Teilen

Je Rezept ein Link ohne Login auf die eigene Version mit Fotos;
Original, Notizen und Kochlog bleiben privat. «Link löschen» beendet
den Zugriff.

## Buchseite fotografieren

Im Import: Foto der Seite, Texterkennung (tesseract, Deutsch und
Englisch) füllt das Formular; Buch und Seite von Hand eintragen.

## Nährwerte

Pro Portion: kcal, Eiweiss, Kohlenhydrate, Fett. Im Formular; beim
Import übernommen, wenn die Seite sie liefert.

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
