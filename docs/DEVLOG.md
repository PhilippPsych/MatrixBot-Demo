# Projekt-DEVLOG – mx-demokratiebot

Dieses Dokument dient zur chronologischen Dokumentation aller wichtigen Schritte im Projekt:
- Server-Setup
- Sicherheit / Hardening
- Matrix/Synapse-Konfiguration
- Bot-Architektur
- Forschung & Betrieb

---

## 2025-11-24 – Projektstart

### Hetzner-Server eingerichtet
- Hetzner Cloud **CX22** gemietet
  - Standort: Falkenstein (DE)
  - Image: **Ubuntu 24.04 LTS**
- SSH-Authentifizierung konfiguriert
  - Neuen SSH-Schlüssel generiert (`ssh-keygen`)
  - **Keine Passphrase** gesetzt
  - Fingerprint beim ersten Login bestätigt
  - Public Key (`id_ed25519.pub`) im Hetzner-Dashboard hinterlegt
  - Root-Login nur via SSH-Key (kein Passwortzugang)
- Firewall noch **nicht** aktiviert (Konfiguration folgt später)
- Erste SSH-Verbindung erfolgreich getestet:
  - `ssh root@<SERVER-IP>`

---

## 2025-11-25 – GitLab & Repository-Struktur

### GitLab eingerichtet
- Neues privates GitLab-Projekt: **mx-demokratiebot**
- Separaten SSH-Key für GitLab erzeugt und hinterlegt
- Lokales Git-Repository initialisiert:
  - `git init`
  - Branch gesetzt: `git branch -m main`

### Erste Projektstruktur erstellt
- Ordner angelegt:
  - `docs/`
  - `bot/`
  - `server/`
- Erste Dokumentationsdatei erstellt: `docs/README.md`
- Änderungen committet:
  - `git add .`
  - `git commit -m "Initial project structure"`
- Verbindung zu GitLab hergestellt und gepusht:
  - `git push -u origin main`

Test-Push funktioniert


### 🔐 Systembenutzer & SSH-Basisabsicherung
- Dedizierten Admin-Benutzer erstellt: **`mxadmin`**
- SSH-Root-Login vollständig deaktiviert  
- SSH-Zugang ausschließlich per **SSH-Key**, keine Passwörter erlaubt
- Folgende Authentifizierungsarten deaktiviert:
  - `PasswordAuthentication no`
  - `KbdInteractiveAuthentication no`
  - `ChallengeResponseAuthentication no`
- SSH-Port auf **2222** geändert (anstatt 22)
- Firewall-Regeln vorher angepasst (2222 geöffnet, alte OpenSSH-Regel entfernt)
- SSH-Dienst neu geladen und Verbindungsaufbau erfolgreich über Port 2222 getestet

### 🔥 Firewall (UFW) konfiguriert
- UFW aktiviert
- Regel gesetzt: `allow 2222/tcp`
- Alte Regeln für Port 22 erfolgreich entfernt
- Ergebnis: Nur Port **2222** ist öffentlich erreichbar  
  → Server akzeptiert ausschließlich sichere SSH-Key-Verbindungen.

### 🚨 Fail2ban installiert & gehärtet
- Fail2ban installiert
- Lokale Konfigurationsdatei `jail.local` erstellt
- Einstellungen:
  - `enabled = true`
  - `maxretry = 3`
  - `bantime = 604800`   (7 Tage)
  - `findtime = 1800`    (30 Minuten)
- Fail2ban gestartet und Status geprüft:  
  → Angriffe werden korrekt erkannt & blockiert.

### 🔄 Automatische Sicherheitsupdates aktiviert
- `unattended-upgrades` aktiviert und konfiguriert
- System installiert künftig automatische Security-Patches
- Auto-Clean & Auto-Remove aktiviert

### 📌 Ergebnis
Der Server ist nun auf einem **sehr hohen Sicherheitsniveau**:
- Kein Root-Login möglich  
- Keine Passwortlogins: SSH nur per Key  
- SSH läuft auf einem nicht-standard Port  
- Firewall minimal & sicher  
- Fail2ban blockt Angriffe zuverlässig  
- Sicherheitsupdates laufen automatisch  
