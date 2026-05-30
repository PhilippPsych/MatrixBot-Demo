# MX-Demokratiebot · Demo

> Dieser Bot wurde im Rahmen eines Forschungsprojekts an der Universität Potsdam entwickelt und wird hier als **Demo-Version** zur Verfügung gestellt. Ziel ist es, die technische Architektur eines Matrix/Element-basierten Chatbot-Systems für den Einsatz in klinisch-psychologischen Interventionsstudien zu demonstrieren.

## Hintergrund

In der klinischen Psychologie und Psychotherapieforschung gewinnen digitale, chatbasierte Interventionen zunehmend an Bedeutung. Dieser Bot demonstriert eine Möglichkeit, solche Interventionen datenschutzkonform, Ende-zu-Ende-verschlüsselt und ohne proprietäre Messenger-Infrastruktur umzusetzen – auf Basis des offenen Matrix-Protokolls.

Die hier abgebildete Intervention richtet sich an Jugendliche und junge Erwachsene und zielt auf die Förderung von Demokratiekompetenz und politischer Offenheit ab. Die Intervention erstreckt sich über zehn Tage und begleitet Teilnehmende durch verschiedene Phasen der Verhaltensänderung (angelehnt an das Transtheoretische Modell).

##Entwicklung
Dieses Projekt wurde in intensiver Zusammenarbeit mit Claude Code (Anthropic) entwickelt. Claude Code hat maßgeblich bei der Architekturentscheidung mitgewirkt.


## Architektur

```
Element X (iOS/Android/Desktop)
        ↓
Matrix/Synapse Server (selbst gehostet, Docker)
        ↓
Nginx Reverse Proxy (HTTPS)
        ↓
Rust Matrix Sidecar (E2EE, Ende-zu-Ende-Verschlüsselung)
        ↓
Python Bot (Interventionslogik)
        ↓
Azure OpenAI (GPT-4.1-mini)
```

**Komponenten:**
- `src/demokratiebot_main.py` – Interventionslogik, Handler-Struktur
- `src/matrix_adapter_sidecar.py` – Matrix-Kommunikation via Rust-Sidecar
- `src/ai_service.py` – LLM-Integration (Azure OpenAI / OpenAI / Mistral)
- `matrix_sidecar/` – Rust-basierter E2EE-Proxy
- `start_bot.sh` / `start_bot_staging.sh` – Startskripte für Production und Staging

## Warum Matrix/Element?

- **Ende-zu-Ende-Verschlüsselung** – Chatverläufe sind für den Server nicht einsehbar
- **Selbst gehostet** – keine Abhängigkeit von kommerziellen Messenger-Diensten
- **DSGVO-konform** – Datenhaltung auf eigener Infrastruktur (Universitätsserver)
- **Offenes Protokoll** – keine Vendor-Lock-in

## Voraussetzungen

- Docker
- Python 3.11+
- Rust (nur für eigenen Sidecar-Build nötig, Binary liegt bei)
- Matrix/Synapse Homeserver
- Azure OpenAI oder OpenAI API-Key

## Konfiguration

Alle Credentials werden über `.env`-Dateien konfiguriert (nie in Git eingecheckt). Eine Beispielkonfiguration findet sich in `.env.staging.example`.

## Hinweis

Dies ist eine Demo-Version. Der produktive Einsatz erfordert eine eigene Server-Infrastruktur, eigene API-Keys und eine angepasste Interventionslogik.

## Kontakt

Philipp Mensah · Universität Potsdam · AG Klinische Psychologie  
pmensah@uni-potsdam.de
