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
