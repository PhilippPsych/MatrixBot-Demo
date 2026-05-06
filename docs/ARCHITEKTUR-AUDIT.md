# Ella-Bot Architekturanalyse & Code-Audit

**Datum:** 2026-05-06
**Erstellt von:** Claude Opus 4.6 + Philipp Mensah
**Codebase-Stand:** Commit c1a2b8f (main)

---

## CHANGELOG — Durchgeführte Fixes

| Datum | Bug | Datei | Änderung | Status |
|-------|-----|-------|----------|--------|
| 2026-05-06 | BUG 1: "be"-Prefix-Falle | `demokratiebot_main.py:1301` | `startswith('be')` ersetzt durch exakte Matches `['bereit', 'ready', 'be']` + Guard: nur triggern wenn keine Intervention aktiv | ✅ Erledigt |
| 2026-05-06 | BUG 6: Doppelter reset-Check | `demokratiebot_main.py:1311-1313` | Doppelten Block entfernt | ✅ Erledigt |

---

## 1. ARCHITEKTUR-ÜBERSICHT (IST-Zustand)

```
┌─────────────────────────────────────────────────────┐
│                    Hetzner Server                    │
│                                                     │
│  ┌──────────────┐     HTTP (8010)    ┌───────────┐  │
│  │  Python Bot   │◄──────────────────►│   Rust    │  │
│  │  (demokratie- │  /send, /events,  │  Sidecar  │  │
│  │  bot_main.py) │  /health          │ (matrix_  │  │
│  │               │                   │  sidecar) │  │
│  │  ┌──────────┐ │                   │           │  │
│  │  │ Scheduler│ │                   │  E2EE +   │  │
│  │  │ (09:00)  │ │                   │  Sync     │  │
│  │  └──────────┘ │                   └─────┬─────┘  │
│  │               │                         │        │
│  │  ┌──────────┐ │                   ┌─────▼─────┐  │
│  │  │ Handlers │ │                   │  Synapse   │  │
│  │  │ (5+Ctrl) │ │                   │  (Docker)  │  │
│  │  └──────────┘ │                   └───────────┘  │
│  └───────┬───────┘                                  │
│          │                                          │
│  ┌───────▼───────┐     ┌──────────────────┐        │
│  │  OpenAI /     │     │  Flat-File       │        │
│  │  Mistral API  │     │  Persistence     │        │
│  │  (ai_service) │     │  (data/*.txt,    │        │
│  └───────────────┘     │   *.json, *.jsonl)│        │
│                        └──────────────────┘        │
└─────────────────────────────────────────────────────┘
```

**Kernkomponenten:**
- **Rust Sidecar** (`matrix_sidecar/`): Matrix E2EE, Sync, DM-Room-Management. HTTP-API fuer Python.
- **Python Bot** (`src/demokratiebot_main.py`): Geschaeftslogik, Routing, Scheduler, State Management.
- **AI Service** (`src/ai_service.py`): Wrapper fuer OpenAI/Mistral API.
- **5 Phasen-Handler** + 1 Control-Handler: Interventionslogik pro TTM-Stufe.
- **Flat-File Persistence**: `.txt` und `.json`-Dateien statt Datenbank.

---

## 2. KRITISCHE BUGS

### BUG 1: "bereit"-Falle blockiert ALLE Nachrichten mit "be..."
**Datei:** `demokratiebot_main.py:1301-1303`
```python
if text_lower.startswith('be') or text_lower == 'ready':
    self.handle_trigger_intervention(message)
    return
```
JEDE Nachricht die mit "be" anfaengt wird abgefangen, bevor die aktive Intervention sie verarbeiten kann. "Beim Lernen...", "Besonders nervt mich..." etc. werden fehlgeleitet.

### BUG 2: Morning-Flow sendet Greeting + startet sofort Intervention
**Datei:** `demokratiebot_main.py:1461-1476`
Morning-Job sendet "Schreibe bereit" und startet dann sofort `start_for_user()`. User bekommt zwei Nachrichten, "bereit" schreiben ist sinnlos (Intervention laeuft bereits), und wenn User "bereit" schreibt greift BUG 1.

### BUG 3: `cleanup_user()` crasht fuer die meisten Handler
**Datei:** `demokratiebot_main.py:364-373`
Nur `AIMaintenanceHandler` hat `_cleanup_state()`. Alle anderen crashen mit AttributeError bei `/stop`.

### BUG 4: `add_engagement_points()` ignoriert den `points`-Parameter
**Datei:** `user_state_points.py:59`
```python
self.engagement_points += 1  # Always 1 point per intervention
```
Alle aufwaendigen Punkte-Berechnungen in Handlern sind wirkungslos.

### BUG 5: Help-Text zeigt Debug-Befehle nur im TEST_MODE
**Datei:** `demokratiebot_main.py:1008`
Befehle sind im PILOT_MODE registriert (Z. 885), aber Help zeigt sie nicht (Z. 1008: `if TEST_MODE` statt `if TEST_MODE or PILOT_MODE`).

### BUG 6: Doppelter `reset`-Check
**Datei:** `demokratiebot_main.py:1309-1312` — identischer Block zweimal.

---

## 3. ARCHITEKTUR-SCHWACHSTELLEN

### 3.1 Hardcoded relative Pfade
`UserState` und alle Handler nutzen `"../data/..."`. Funktioniert nur wenn CWD = `src/`.

### 3.2 Zwei Matrix-Adapter (einer Dead Code)
- `matrix_adapter_sidecar.py` — aktuell genutzt
- `matrix_adapter.py` — Dead Code (nio-basiert)

### 3.3 Zwei Rust-Sidecar-Implementierungen
- `matrix_sidecar/` — aktuell (EventQueue, Long-Polling)
- `rust-sidecar/` — alt (einfache Queue)

### 3.4 Flat-File Persistence ohne Locking
Kein File-Locking, kein atomares Schreiben, O(n)-Lookups in user_data.txt.

### 3.5 Keine Thread-Safety bei Sessions
Handler-Sessions (in-memory Dict) ohne Locking zwischen Polling-Thread und Scheduler-Thread.

---

## 4. INKONSISTENZEN

### 4.1 Intervention-History nur teilweise implementiert
| Handler | History-Tracking |
|---------|:---:|
| Precontemplation | Ja |
| Contemplation | **Nein** |
| Preparation | **Nein** |
| Action | **Nein** |
| Maintenance | **Nein** |

### 4.2 Handler-Architektur-Wildwuchs
Drei verschiedene Architekturen parallel:
1. Eigene Klasse (Precontemplation, Contemplation)
2. Eigene Klasse mit Modus-System (Preparation, Action)
3. Generische Basisklasse `AIPhaseHandler` (wird nie verwendet, Dead Code)

### 4.3 Trailing-Comma-Fix inkonsistent
Nur in `generic_ai_handler.py` und `precontemplation_handler_ai.py`. Fehlt in 4 anderen Handlern. Bricht Mistral-Migration.

### 4.4 MAX_INTERACTIONS-Inkonsistenz
Precontemplation: Code sagt 5, Docstring sagt 3.

### 4.5 `study_manager` wird uebergeben aber nie genutzt
Alle `advance_day`-Aufrufe sind auskommentiert (`pass`).

---

## 5. STAERKEN

1. **Solides therapeutisches Framework**: TTM-Phasen mit passenden Techniken (MI, kognitive Umstrukturierung, Behavioral Rehearsal)
2. **Robuste Fallback-Kette**: Fallback-Interventions + Emergency-Complete bei AI-Ausfall
3. **Rust-Sidecar-Architektur**: Saubere Trennung E2EE (Rust) vs. Geschaeftslogik (Python)
4. **Crisis Detection**: Erkennt Krisensprache und gibt Hilfe-Ressourcen
5. **Re-Evaluation-System**: Punkt-basiert alle 10 Punkte
6. **Kontrollbedingung sauber getrennt**: Minimal, neutral, methodisch korrekt
7. **Dual-Provider-Support**: OpenAI + Mistral ueber dasselbe Interface

---

## 6. ROADMAP

### Phase 1: Kritische Bugfixes (Sonnet, 1-2 Tage)
1. "be"-Prefix-Bug fixen
2. Morning-Flow reparieren
3. `add_engagement_points()` fixen
4. `_cleanup_state()` ueberall hinzufuegen
5. Help-Text PILOT_MODE
6. Doppelter reset-Check

### Phase 2: History-System vervollstaendigen (Sonnet, 1 Tag)
7. `add_intervention_to_history()` in Contemplation, Preparation, Action, Maintenance

### Phase 3: Konsistenz & Robustheit (Sonnet + Opus, 2-3 Tage)
8. Trailing-Comma-Fix ueberall (Sonnet)
9. Relative Pfade → BASE_DIR (Sonnet)
10. Dead Code entfernen (Sonnet)
11. **Handler-Architektur vereinheitlichen (Opus)**
12. AIService Singleton (Sonnet)

### Phase 4: Datenpersistenz (Opus, 2-3 Tage)
13. **SQLite-Migration (Opus)**
14. File-Locking als Uebergangsloesung (Sonnet)

### Phase 5: UX & Wissenschaftliche Qualitaet (Opus, 2-3 Tage)
15. **Morning-Flow Redesign mit Waiting-Mechanismus (Opus)**
16. **Multi-Day Learning (Opus)**
17. Varianz-Tracking (Sonnet)

### Phase 6: Infrastruktur (Sonnet, optional)
18. Unit-Tests
19. Logging-Konsolidierung
20. Monitoring
21. Mistral-Migration testen

---

## 7. MODELL-EMPFEHLUNG PRO TASK

| Task-Typ | Modell | Grund |
|----------|--------|-------|
| Lokale Bugfixes, Pattern kopieren | **Sonnet** | Klar definiert, mechanisch |
| Architektur-Redesign, Schema-Design | **Opus** | Designentscheidungen mit Tradeoffs |
| Dead-Code-Entfernung, Konsistenz | **Sonnet** | Loeschen und angleichen |
| Neues Feature-Design (Multi-Day) | **Opus** | Promptdesign + Datenmodell + UX |
