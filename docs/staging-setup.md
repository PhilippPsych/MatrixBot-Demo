# Staging-Umgebung einrichten

## Voraussetzungen
- Produktions-Bot läuft bereits
- SSH-Zugang zum Server (`ssh mxadmin@<SERVER-IP> -p 2222`)

---

## Schritt 1 – Staging-Matrix-Account erstellen

Auf dem Server als Admin einen zweiten Bot-User anlegen:

```bash
docker exec -it synapse register_new_matrix_user \
  -u ella-staging \
  -p <SICHERES_PASSWORT> \
  -c /data/homeserver.yaml \
  http://localhost:8008
```

Dann einmalig Access-Token und Device-ID holen:

```bash
curl -s -X POST https://demokratiebot.de/_matrix/client/v3/login \
  -H "Content-Type: application/json" \
  -d '{"type":"m.login.password","user":"ella-staging","password":"<PASSWORT>"}' \
  | jq '{access_token, device_id}'
```

→ `access_token` und `device_id` notieren, werden in `.env.staging` eingetragen.

---

## Schritt 2 – Staging-Verzeichnis anlegen

```bash
cp -r /home/mxbotlab-admin/mx/bots/demokratiebot \
      /home/mxbotlab-admin/mx/bots/demokratiebot-staging
```

Sidecar-Store leeren (neuer Account braucht frischen Store):
```bash
rm -rf /home/mxbotlab-admin/mx/bots/demokratiebot-staging/matrix_sidecar/store
mkdir  /home/mxbotlab-admin/mx/bots/demokratiebot-staging/matrix_sidecar/store
```

Data-Verzeichnis leeren (frische Staging-Daten):
```bash
rm -rf /home/mxbotlab-admin/mx/bots/demokratiebot-staging/data
mkdir -p /home/mxbotlab-admin/mx/bots/demokratiebot-staging/data/user_states
mkdir -p /home/mxbotlab-admin/mx/bots/demokratiebot-staging/data/logs
```

---

## Schritt 3 – .env.staging anlegen

```bash
cd /home/mxbotlab-admin/mx/bots/demokratiebot-staging
cp .env.staging.example .env.staging
nano .env.staging
```

Werte eintragen:
- `MATRIX_ACCESS_TOKEN` → aus Schritt 1
- `MATRIX_DEVICE_ID` → aus Schritt 1
- `ANTHROPIC_API_KEY` → gleicher Key wie Prod (oder separater)

---

## Schritt 4 – Startup-Script ausführbar machen & starten

```bash
chmod +x start_bot_staging.sh
bash start_bot_staging.sh
```

---

## Schritt 5 – Prüfen ob alles läuft

```bash
# Alle Screens anzeigen (prod + staging sollten beide sichtbar sein)
screen -ls

# Staging-Bot-Log live verfolgen
screen -r ella-staging

# Staging-Sidecar-Log
screen -r sidecar-staging
```

Erwartetes Ergebnis:
```
There are screens on:
    XXXX.sidecar         (prod)
    XXXX.ella-bot        (prod)
    XXXX.sidecar-staging (staging)
    XXXX.ella-staging    (staging)
```

Screen verlassen ohne zu stoppen: `Ctrl+A`, dann `D`

---

## Staging updaten (nach Code-Änderungen)

```bash
cd /home/mxbotlab-admin/mx/bots/demokratiebot-staging
git pull origin main
bash start_bot_staging.sh
```

Das Script stoppt nur die Staging-Screens — Produktion bleibt unberührt.

---

## Staging stoppen

```bash
screen -S ella-staging -X quit
screen -S sidecar-staging -X quit
```

---

## Wichtige Unterschiede Prod vs. Staging

| | Produktion | Staging |
|---|---|---|
| Verzeichnis | `demokratiebot` | `demokratiebot-staging` |
| Matrix-User | `@ella:demokratiebot.de` | `@ella-staging:demokratiebot.de` |
| Sidecar-Port | `8010` | `8011` |
| Screen-Namen | `sidecar`, `ella-bot` | `sidecar-staging`, `ella-staging` |
| TEST_MODE | `false` | `true` |
| `.env`-Datei | `.env` | `.env.staging` |
