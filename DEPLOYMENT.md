# Deployment-Workflow: Staging → Production

## Branches

| Branch | Server-Verzeichnis | Bot-Screens | Port |
|--------|-------------------|-------------|------|
| `staging` | `/home/mxbotlab-admin/mx/bots/demokratiebot-staging/` | `sidecar-staging`, `ella-staging` | 8011 |
| `main` | `/home/mxbotlab-admin/mx/bots/demokratiebot/` | `sidecar`, `ella-bot` | 8010 |

---

## Lokaler Workflow (Standard)

### 1. Änderungen lokal entwickeln (auf `staging`)
```bash
git checkout staging
# ... Code ändern ...
git add src/datei.py
git commit -m "fix: beschreibung der änderung"
git push origin staging
```

### 2. Staging auf Server deployen und testen
```bash
ssh mxbotlab-admin@78.46.152.202

# Im Staging-Verzeichnis
cd ~/mx/bots/demokratiebot-staging
git pull origin staging

# Staging-Bot neu starten
~/mx/bots/demokratiebot-staging/start_bot_staging.sh

# Logs prüfen
screen -r ella-staging
```

### 3. Wenn Staging OK → in Production mergen
```bash
# Lokal: staging → main mergen
git checkout main
git merge staging
git push origin main
```

### 4. Production auf Server deployen
```bash
ssh mxbotlab-admin@78.46.152.202

cd ~/mx/bots/demokratiebot
git pull origin main

# Production-Bot neu starten
~/mx/bots/demokratiebot/start_bot.sh
```

---

## Schnell-Referenz: Server-Befehle

```bash
# Status beider Bots
screen -ls
curl -s http://127.0.0.1:8010/health | python3 -m json.tool   # Production
curl -s http://127.0.0.1:8011/health | python3 -m json.tool   # Staging

# Logs live
screen -r ella-staging     # Staging-Bot
screen -r ella-bot         # Production-Bot
screen -r sidecar-staging  # Staging-Sidecar
screen -r sidecar          # Production-Sidecar
# Detachen: Ctrl+A, D

# Nur Staging neu starten (Production bleibt unberührt)
screen -S sidecar-staging -X quit 2>/dev/null; screen -S ella-staging -X quit 2>/dev/null
~/mx/bots/demokratiebot-staging/start_bot_staging.sh

# Nur Production neu starten
screen -S sidecar -X quit 2>/dev/null; screen -S ella-bot -X quit 2>/dev/null
~/mx/bots/demokratiebot/start_bot.sh
```

---

## Wichtige Regeln

1. **Niemals direkt auf `main` entwickeln** — immer über `staging`
2. **Niemals `main` auf Server deployen ohne vorherigen Staging-Test**
3. **`.env` und `.env.staging` sind NICHT im Git** — müssen auf Server manuell gepflegt werden
4. **Staging und Production haben getrennte `data/`-Verzeichnisse** — Testdaten beeinflussen keine echten Studienteilnehmer

---

## Einmalige Server-Einrichtung (bereits erledigt)

Auf dem Server muss das Staging-Verzeichnis den `staging`-Branch tracken:
```bash
cd ~/mx/bots/demokratiebot-staging
git remote set-url origin git@github.com:PhilippPsych/MX-Demokratiebox.git
git fetch origin
git checkout staging
git branch --set-upstream-to=origin/staging staging
```

Production trackt `main` (Standard, bereits so eingerichtet).
