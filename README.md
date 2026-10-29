# Rezepte-App

Private Rezeptsammlung für eine Person, gemacht für das Handy in der
Küche. Läuft auf einem eigenen Server mit Docker, ohne Cloud-Dienste.

## Was ist das

Die App besteht aus vier Containern, die zusammen in `compose.yaml`
beschrieben sind:

| Container | Aufgabe |
|-----------|---------|
| `web`     | Caddy: liefert die Oberfläche aus, leitet `/api` ans Backend weiter und besorgt automatisch das HTTPS-Zertifikat (Let's Encrypt) |
| `api`     | FastAPI (Python): die ganze Logik, spielt beim Start die Datenbank-Migrationen selbst ein |
| `db`      | PostgreSQL: die Datenbank in einem Docker-Volume |
| `backup`  | Erstellt täglich einen Datenbank-Dump und ein Archiv der Fotos nach `./backups` und löscht alte Dateien |

In Phase 1 kann man sich anmelden, Rezepte erfassen, anzeigen,
bearbeiten und löschen sowie nach Kategorie, Tags, Zutaten und Text
filtern. Jedes Rezept hat ein unveränderliches Original und eine eigene,
bearbeitbare Version.

### Geplant

Noch nicht gebaut, kommt in späteren Phasen: Kochmodus, Notizen,
«gekocht am» mit Bewertung, Fotos, Export als ZIP, Import per URL.

## Voraussetzungen

- Ein Linux-Server (z. B. ein kleiner VPS) mit installiertem Docker
  inklusive `docker compose` (Docker Engine 24 oder neuer).
- Eine Domain (z. B. `rezepte.example.ch`), deren DNS-Eintrag (A- bzw.
  AAAA-Record) auf die IP-Adresse des Servers zeigt.
- Die Ports 80 und 443 des Servers sind aus dem Internet erreichbar
  (Firewall des Anbieters prüfen). Caddy braucht beide, um das
  Zertifikat zu holen und zu erneuern.
- `git` auf dem Server.

## Installation in drei Schritten

### 1. Repository holen

```bash
git clone <URL-dieses-Repositories> rezepte-app
```

```bash
cd rezepte-app
```

### 2. Einstellungen ausfüllen

```bash
cp .env.example .env
```

Dann `.env` mit einem Editor öffnen (z. B. `nano .env`) und die zwei
Pflichtwerte setzen:

- `DOMAIN`: die Domain ohne `https://`, z. B. `rezepte.example.ch`
- `DB_PASSWORD`: ein langes, zufälliges Passwort (ohne Dollarzeichen).
  Vorschlag erzeugen mit `openssl rand -hex 24`.

Alles andere hat sinnvolle Vorgaben und ist in `.env.example`
erklärt. Fehlt ein Pflichtwert, bricht der Start mit einem klaren
Hinweis ab («DOMAIN fehlt in .env»).

### 3. Starten

```bash
docker compose up -d --build
```

Baut die Container aus dem Repository (`--build`), startet sie im
Hintergrund (`-d`) und richtet Datenbank und Volumes ein. Der erste Start
dauert einige Minuten, weil die Images gebaut werden und Caddy das
Zertifikat holt.

Danach ist die App unter `https://DOMAIN` erreichbar. Der Status der
vier Container:

```bash
docker compose ps
```

Zeigt alle Container des Stacks mit Zustand (`running`, `healthy`).

## Benutzer anlegen

Die App hat genau einen Benutzer. Er wird einmal im Container angelegt:

```bash
docker compose exec api python -m app.cli create-user NAME
```

Führt den Befehl im laufenden `api`-Container aus; er fragt nach dem
Passwort und legt den Benutzer `NAME` an. Danach kann man sich im
Browser anmelden.

Passwort später ändern:

```bash
docker compose exec api python -m app.cli set-password NAME
```

Alle Anmeldungen auf allen Geräten beenden (z. B. nach Verlust des
Handys):

```bash
docker compose exec api python -m app.cli purge-sessions
```

## Handy-Zugriff und Installation als App

Im Handy-Browser `https://DOMAIN` öffnen und anmelden. Die Anmeldung
bleibt 30 Tage gültig (`SESSION_DAYS`).

Die App ist eine PWA und lässt sich wie eine normale App auf den
Startbildschirm legen; sie öffnet dann ohne Browserleiste im Vollbild:

- **iPhone (Safari):** Teilen-Symbol (Quadrat mit Pfeil) antippen, dann
  «Zum Home-Bildschirm».
- **Android (Chrome):** Menü (drei Punkte) antippen, dann
  «App installieren» bzw. «Zum Startbildschirm hinzufügen».

## Alltagsbefehle

Alle Befehle im Ordner `rezepte-app` ausführen.

Status der Container:

```bash
docker compose ps
```

Logs live mitlesen (beenden mit Ctrl+C):

```bash
docker compose logs -f
```

Zeigt die Ausgaben aller Container; mit einem Namen dahinter nur einen,
z. B. `docker compose logs -f api`.

Update auf die neuste Version:

```bash
git pull && docker compose up -d --build
```

Holt den neuen Code und baut nur die Container neu, die sich geändert
haben; Datenbank und Fotos bleiben erhalten, Migrationen laufen beim
Start automatisch.

Stoppen (Daten bleiben erhalten):

```bash
docker compose down
```

Hält alle Container an und entfernt sie; Volumes (Datenbank, Fotos,
Zertifikate) bleiben bestehen. Niemals `docker compose down -v`
ausführen, das löscht die Volumes und damit alle Daten.

Wieder starten:

```bash
docker compose up -d
```

Einzelnen Container neu starten, z. B. nach einer Änderung in `.env`:

```bash
docker compose up -d api
```

Startet nur `api` neu und übernimmt dabei geänderte Einstellungen.

## Backup

### Was automatisch passiert

Der Container `backup` läuft dauernd mit und erstellt täglich um
`BACKUP_HOUR` Uhr (Vorgabe 3 Uhr, Zeitzone `TZ`) zwei Dateien im Ordner
`./backups` auf dem Server:

- `db-JJJJMMTT-HHMMSS.dump`: vollständiger Datenbank-Dump
  (`pg_dump`, komprimiertes Format)
- `media-JJJJMMTT-HHMMSS.tar.gz`: Archiv aller Fotos (wird erst
  geschrieben, wenn Fotos vorhanden sind)

Dateien, die älter als `BACKUP_KEEP_DAYS` Tage sind (Vorgabe 14), werden
gelöscht. Jede Aktion steht als eine Zeile im Log:

```bash
docker compose logs backup
```

Wichtig: `./backups` liegt auf demselben Server. Für ein echtes Backup
den Ordner regelmässig an einen anderen Ort kopieren, z. B. vom eigenen
Rechner aus:

```bash
rsync -av BENUTZER@SERVER:rezepte-app/backups/ ./rezepte-backups/
```

### Backup von Hand

```bash
docker compose run --rm backup now
```

Startet einen zusätzlichen, einmaligen `backup`-Container, der sofort ein
Backup schreibt und sich danach wieder entfernt (`--rm`).

## Wiederherstellen

Voraussetzung: der Stack läuft (`docker compose up -d --build` ist
durch) und die Backup-Dateien liegen in `./backups`. `DATUM` steht unten
für den Zeitstempel im Dateinamen, z. B. `20261029-030000`.

### 1. API anhalten

```bash
docker compose stop api
```

Hält nur den `api`-Container an, damit während der Wiederherstellung
niemand in die Datenbank schreibt.

### 2. Datenbank zurückspielen

```bash
docker compose exec -T db pg_restore -U rezepte -d rezepte --clean --if-exists --no-owner < backups/db-DATUM.dump
```

Liest den Dump vom eigenen Rechner (`-T`, Eingabe über die Konsole) und
spielt ihn im `db`-Container ein; vorhandene Tabellen werden vorher
gelöscht (`--clean`). Einzelne Meldungen über nicht vorhandene Objekte
sind normal.

### 3. Fotos zurückspielen (nur wenn ein `media-`Archiv vorhanden ist)

```bash
docker compose run --rm --entrypoint tar -v "$PWD/backups:/backups" api -xzf /backups/media-DATUM.tar.gz -C /data
```

Startet einen einmaligen Container mit dem Foto-Volume und entpackt das
Archiv dort hinein (`--entrypoint tar` ersetzt den normalen Start der
API durch den Entpack-Befehl).

### 4. Alles wieder starten

```bash
docker compose up -d
```

Startet `api` wieder; falls der Dump von einer älteren Programmversion
stammt, bringen die Migrationen die Datenbank beim Start automatisch auf
den aktuellen Stand.

## Umzug auf einen anderen Server

1. Auf dem alten Server ein frisches Backup erstellen:

   ```bash
   docker compose run --rm backup now
   ```

2. Vom alten Server die Datei `.env` und den Ordner `backups/` sichern,
   z. B. mit `scp` oder `rsync`.

3. Auf dem neuen Server die Installation wie oben durchführen
   (`git clone`, `.env` hinüberkopieren, `docker compose up -d --build`).
   Die Domain darf dabei noch auf den alten Server zeigen; Caddy
   versucht das Zertifikat einfach erneut, sobald DNS stimmt.

4. Den Ordner `backups/` in den Ordner `rezepte-app` auf dem neuen
   Server kopieren und die Schritte unter «Wiederherstellen» ausführen.

5. DNS der Domain auf den neuen Server umstellen. Innert einiger Minuten
   holt Caddy das Zertifikat; danach den alten Server mit
   `docker compose down` stoppen.

## Entwicklung

Für die Arbeit am Code gibt es `compose.dev.yaml`. In `.env`
`DOMAIN=localhost` setzen und dann:

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

Startet den Stack im Vordergrund mit Entwicklungs-Einstellungen: der
Code aus `backend/app` und `frontend/site` ist in die Container
eingebunden (Änderungen wirken ohne Neubau, die API lädt automatisch
neu), die Datenbank ist auf `localhost:5432` erreichbar, und die
API-Dokumentation ist unter `https://localhost/api/docs` eingeschaltet.
Mit `DOMAIN=localhost` stellt Caddy ein eigenes Zertifikat aus; der
Browser warnt einmal, danach funktioniert HTTPS wie in Produktion.

Tests des Backends (ohne Docker, mit lokalem Python 3.12):

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt && .venv/bin/pytest
```

Richtet einmal eine virtuelle Python-Umgebung ein, installiert die
Abhängigkeiten und führt die Tests aus; später genügt
`cd backend && .venv/bin/pytest`.

## Fehlersuche

**Seite nicht erreichbar oder Zertifikatsfehler:** Caddy bekommt das
Zertifikat nur, wenn die Domain per DNS auf den Server zeigt und die
Ports 80 und 443 von aussen offen sind. Prüfen mit:

```bash
docker compose logs web
```

Zeigt die Caddy-Meldungen; bei Problemen mit dem Zertifikat stehen dort
Hinweise wie «DNS problem» oder «connection refused».

**Ein Container startet nicht:**

```bash
docker compose ps
```

Zeigt den Zustand; ein Container mit `restarting` oder `exited` hat ein
Problem. Dann die Logs des betroffenen Containers lesen, z. B.
`docker compose logs api`.

**Start bricht mit «DOMAIN fehlt in .env» oder «DB_PASSWORD fehlt in
.env» ab:** Die Datei `.env` fehlt oder der Wert ist leer. Siehe
Schritt 2 der Installation.

**Passwort vergessen:** Neu setzen mit
`docker compose exec api python -m app.cli set-password NAME`.

**Datenbank-Passwort geändert:** `DB_PASSWORD` in `.env` darf nach dem
ersten Start nicht mehr geändert werden, da PostgreSQL das Passwort im
Volume gespeichert hat. Falls doch nötig: im `db`-Container mit
`docker compose exec db psql -U rezepte -c "ALTER USER rezepte PASSWORD 'NEU';"`
zuerst in der Datenbank ändern, dann `.env` anpassen und
`docker compose up -d` ausführen.
