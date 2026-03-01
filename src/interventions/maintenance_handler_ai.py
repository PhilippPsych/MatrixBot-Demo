#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Powered Maintenance Handler v2.1
FIXES: Expliziter Offenheits-Fokus + adaptives "nichts eingefallen" Handling
"""

import logging
import json
from typing import Dict, Optional
from datetime import datetime
from ai_service import AIService
from user_state_points import UserState

logger = logging.getLogger(__name__)


class AIMaintenanceHandler:
    """
    AI-gesteuerter Maintenance Handler für Stabilisierung von Offenheit
    
    Phase-Ziel: Offenheit für andere Meinungen stabilisieren (wenig missionarisch)
    
    Techniken:
    - Relapse Prevention: Rückfälle erkennen und vorbereiten
    - Selbstmanagement: Eigene Strategien entwickeln
    - Peer Support: Erfahrungen teilen, anderen helfen
    - Ressourcenaktivierung: Was funktioniert bereits
    
    Übungen (max. 3 Interaktionen):
    1. Erfolge mit OFFENHEIT reflektieren (Wo warst du offen?)
    2. Schwere Momente mit OFFENHEIT (Wann fällt's schwer?)
    3. Tipps für OFFENHEIT sammeln (Was hilft anderen?)
    
    KRITISCH: IMMER Fokus auf "Offenheit für andere Meinungen"!
    """
    
    MAX_INTERACTIONS = 3  # Harte Grenze
    
    def __init__(self, bot_instance, study_manager=None):
        self.bot = bot_instance
        self.study_manager = study_manager
        self.ai = AIService()
        self.sessions: Dict[str, Dict] = {}
    
    def start_intervention(self, phone_number: str) -> bool:
        """Startet Maintenance mit explizitem Offenheits-Fokus"""
        if phone_number in self.sessions:
            logger.warning(f"Maintenance already active for {phone_number}")
            return False
        
        user_state = UserState.load(phone_number)
        
        # AI generiert Opening für Schritt 1: Erfolge MIT OFFENHEIT
        opening = self._generate_opening(user_state)
        
        # Initialisiere Session mit Interaktionszähler
        self.sessions[phone_number] = {
            "start_time": datetime.now().isoformat(),
            "conversation": [],
            "interaction_count": 0,
            "step": 1,  # Welche Übung: 1=Erfolge, 2=Schwere Momente, 3=Tipps
            "had_nothing": False,  # Flag: User hatte "nichts" zu berichten
            "data": {
                "successes": [],      # Erfolge mit Offenheit
                "challenges": [],     # Schwere Momente mit Offenheit
                "tips": [],          # Tipps für Offenheit
                "strategies": []     # Strategien für Offenheit
            },
            "user_state_snapshot": {
                "level": user_state.level,
                "points": user_state.engagement_points,
                "total_interventions": user_state.total_interventions
            }
        }
        
        # Sende Opening
        self.bot.send_message(phone_number, opening)
        self._add_to_conversation(phone_number, "assistant", opening)
        
        return True
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Verarbeitet Antwort mit adaptivem Nachfragen"""
        if phone_number not in self.sessions:
            return False
        
        session = self.sessions[phone_number]
        
        # Inkrementiere Interaktionszähler
        session["interaction_count"] += 1
        self._add_to_conversation(phone_number, "user", text)
        
        try:
            # Prüfe Interaktions-Limit
            if session["interaction_count"] >= self.MAX_INTERACTIONS:
                # Letzte Interaktion - muss abschließen
                self._force_complete_intervention(phone_number, text)
                return True
            
            # AI analysiert und steuert nächsten Schritt (adaptiv!)
            ai_decision = self._ai_process_response(phone_number, text, session)
            
            if ai_decision["action"] == "continue":
                # Weitermachen (nur wenn nicht am Limit)
                self.bot.send_message(phone_number, ai_decision["message"])
                self._add_to_conversation(phone_number, "assistant", ai_decision["message"])
                
                # Update Schritt wenn AI es vorschlägt
                if "next_step" in ai_decision:
                    session["step"] = ai_decision["next_step"]
                
                # Speichere extrahierte Daten
                if "extracted_data" in ai_decision:
                    self._update_session_data(session, ai_decision["extracted_data"])
                
                # Markiere wenn User "nichts" hatte
                if "user_had_nothing" in ai_decision:
                    session["had_nothing"] = ai_decision["user_had_nothing"]
                
            elif ai_decision["action"] == "complete":
                # Vorzeitiger Abschluss (User hat alles gut beantwortet)
                self._complete_intervention(phone_number, ai_decision)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in Maintenance: {e}")
            self._emergency_complete(phone_number)
            return False
    
    def _generate_opening(self, user_state: UserState) -> str:
        """AI generiert Opening mit EXPLIZITEM Offenheits-Fokus"""
        
        prompt = f"""Du bist ELLA, ein Coach für Jugendliche und junge Erwachsene (11-25 Jahre).
Eröffne eine Maintenance-Intervention zur Stabilisierung von OFFENHEIT FÜR ANDERE MEINUNGEN.

**KRITISCH: EXPLIZITER FOKUS AUF OFFENHEIT!**

ZIEL VON SCHRITT 1:
User reflektiert Erfolge - wo war er letzte Woche OFFEN für ANDERE MEINUNGEN?
(NICHT allgemeine Herausforderungen - nur OFFENHEIT!)

USER-PROFIL:
- Level: {user_state.level}
- Punkte: {user_state.engagement_points}
- Phase: Maintenance (Offenheit stabilisieren)

TECHNIKEN:
- Ressourcenaktivierung: Was funktioniert bei OFFENHEIT bereits?
- Peer Support: Erfahrungen mit OFFENHEIT teilen
- Selbstmanagement: Eigene Stärken bei OFFENHEIT

AUFGABE:
Formuliere ein kurzes Check-in (2-3 Sätze), das:
- EXPLIZIT nach OFFENHEIT für ANDERE MEINUNGEN fragt
- Nach Situationen fragt wo User OFFEN war (beim Lernen, im Alltag, mit Freunden)
- Konkret und niedrigschwellig ist
- Nicht missionarisch, sondern neugierig

WICHTIG:
- Jugendgerecht (11-25 Jahre)
- NIEMALS "Schule/Studium/Klasse" - stattdessen: "beim Lernen", "im Alltag", "in Gruppen"
- Supportiv (Peer Support!)
- MUSS das Wort "Offenheit" oder "offen" oder "andere Meinung" enthalten!

BEISPIEL-STIL:
"Hey! Kurzes Check-in: Gab's letzte Woche eine Situation, wo du offen für eine andere Meinung warst? Erzähl kurz!"

ODER:

"Hallo! Wie lief's diese Woche mit Offenheit? Gab's einen Moment, wo du einer anderen Meinung zugehört hast?"

Antworte NUR mit der Nachricht, kein JSON."""
        
        result = self.ai._make_request(prompt, max_tokens=200, temperature=0.8)
        
        # Sicherheit: Prüfe ob "offen" oder "Meinung" im Text
        if result and ("offen" in result.lower() or "meinung" in result.lower()):
            return result
        else:
            return "Hey! Kurzes Check-in: Gab's letzte Woche eine Situation, wo du offen für eine andere Meinung warst?"
    
    def _ai_process_response(self, phone_number: str, text: str, session: Dict) -> Dict:
        """AI analysiert Antwort ADAPTIV mit besserem "nichts" Handling"""
        
        conversation = self._format_conversation(session["conversation"])
        current_step = session["step"]
        interaction_count = session["interaction_count"]
        remaining = self.MAX_INTERACTIONS - interaction_count
        data = session["data"]
        had_nothing_before = session.get("had_nothing", False)
        
        # Erkenne "nichts eingefallen" Signale
        nothing_signals = ["nichts", "weiß nicht", "keine ahnung", "fällt mir nicht ein", 
                          "kann mich nicht erinnern", "nicht wirklich", "keine situation"]
        user_said_nothing = any(signal in text.lower() for signal in nothing_signals)
        
        prompt = f"""Du bist ELLA in einer Maintenance-Intervention zur Stabilisierung von OFFENHEIT.

**KRITISCHER FOKUS: Nur OFFENHEIT für ANDERE MEINUNGEN - nichts anderes!**

**HARTER LIMIT: Nur noch {remaining} ELLA-Antworten möglich!**

TECHNIKEN:
- Relapse Prevention: Rückfälle bei OFFENHEIT vorbereiten
- Selbstmanagement: Strategien für OFFENHEIT
- Peer Support: Erfahrungen mit OFFENHEIT teilen
- Ressourcenaktivierung: Was funktioniert bei OFFENHEIT

ZIEL:
OFFENHEIT FÜR ANDERE MEINUNGEN stabilisieren - supportiv, nicht missionarisch!

3-SCHRITT STRUKTUR (immer zu OFFENHEIT):
1. Erfolge mit OFFENHEIT (Wo warst du offen für andere Meinungen?)
2. Schwere Momente mit OFFENHEIT (Wann fällt's schwer offen zu sein?)
3. Tipps für OFFENHEIT (Was hilft dir/anderen offen zu bleiben?)

AKTUELLER SCHRITT: {current_step}/3
INTERAKTION: {interaction_count}/{self.MAX_INTERACTIONS}

GESAMMELTE DATEN:
- Erfolge mit Offenheit: {len(data.get('successes', []))}
- Schwere Momente: {len(data.get('challenges', []))}
- Tipps: {len(data.get('tips', []))}

USER HATTE VORHER "NICHTS": {had_nothing_before}

DIALOG:
{conversation}

USER: "{text}"

**ADAPTIVES "NICHTS EINGEFALLEN" HANDLING:**

User hat wahrscheinlich "nichts" gesagt wenn:
- Text enthält: "nichts", "weiß nicht", "keine Ahnung", "fällt mir nicht ein"
- Sehr kurze Antwort (<15 Zeichen)
- Ausweichend

**WENN USER "NICHTS" GESAGT HAT:**
1. **AKZEPTIERE ES!** Nicht nachbohren oder nerven
2. Validiere: "Alles klar, manchmal gibt's gerade keine passende Situation."
3. Gehe zum nächsten Schritt über (OHNE Drama)
4. Setze "user_had_nothing": true im JSON

**ENTSCHEIDUNGSLOGIK - ADAPTIV:**

**Interaktion 1 (gerade passiert):**
- Wenn Erfolg mit OFFENHEIT genannt → CONTINUE zu Schritt 2 (Schwere Momente)
- Wenn "nichts"/ausweichend → AKZEPTIERE und CONTINUE zu Schritt 2 mit: "Kein Problem! Manchmal fällt's schwer, sich an was zu erinnern. Andere Frage: Wann wird's bei dir schwierig, offen zu bleiben?"
- Wenn User über was ANDERES spricht (nicht Offenheit) → Sanft zurücklenken: "Interessant! Und wie war's speziell mit Offenheit für andere Meinungen?"

**Interaktion 2 (gerade passiert):**
- Wenn schwerer Moment mit OFFENHEIT genannt → CONTINUE zu Schritt 3 (Tipps)
- Wenn wieder "nichts" → AKZEPTIERE und CONTINUE zu Schritt 3: "Verstehe! Dann anders: Was könnte anderen helfen, wenn's schwierig wird offen zu bleiben?"
- User MUSS jetzt bei Schritt 3 sein!

**Interaktion 3 (LETZTE - gerade passiert):**
- IMMER COMPLETE
- Sammle Tipp falls gegeben
- Auch wenn User wenig geteilt hat - wertschätze das Check-in!

WICHTIG FÜR CONTINUE:
- 1-2 Sätze maximum
- Bei "nichts" → kurz validieren, dann weiter
- IMMER Fokus auf OFFENHEIT (nie allgemeine Sachen!)
- Konkrete Fragen zu OFFENHEIT
- NIEMALS "Schule/Studium"
- Peer Support Ton: supportiv, nicht belehrend

ANTWORT (JSON):
{{
    "action": "continue|complete",
    "message": "Deine supportive Nachricht (1-2 Sätze, bei continue)",
    "next_step": 1-3,
    "extracted_data": {{
        "successes": ["Erfolg mit Offenheit"],
        "challenges": ["Schwierigkeit mit Offenheit"],
        "tips": ["Tipp für Offenheit"]
    }},
    "user_had_nothing": true/false,
    "points": 1-2,
    "reasoning": "Kurze Begründung"
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=400, temperature=0.8)
        parsed = self._parse_json(response, {
            "action": "complete",
            "message": "",
            "points": 1,
            "reasoning": "fallback"
        })
        
        # Automatische Erkennung wenn AI "nichts" nicht erkannt hat
        if user_said_nothing and "user_had_nothing" not in parsed:
            parsed["user_had_nothing"] = True
            logger.info(f"Auto-detected 'nothing' response: {text}")
        
        return parsed
    
    def _force_complete_intervention(self, phone_number: str, last_text: str):
        """Erzwingt Abschluss nach 3. Interaktion"""
        session = self.sessions[phone_number]
        
        # Versuche noch Daten aus letzter Antwort zu extrahieren
        self._extract_final_data(session, last_text)
        
        # Generiere supportiven Abschluss
        closing = self._generate_closing(session)
        self.bot.send_message(phone_number, closing)
        
        # Points vergeben (auch wenn User wenig teilte!)
        points = 2 if session["data"]["successes"] and session["data"]["challenges"] else 1
        
        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(points, self.bot)
        
        # Daten speichern
        self._save_session_data(phone_number, session, points)
        
        # Cleanup
        if self.study_manager:

            pass  # advance_day disabled - day advances by real time only

        

        del self.sessions[phone_number]
        logger.info(f"Maintenance force-completed for {phone_number}: {points} points")
    
    def _complete_intervention(self, phone_number: str, ai_decision: Dict):
        """Schließt Intervention vorzeitig ab (User hat gut geantwortet)"""
        session = self.sessions[phone_number]
        
        # Speichere extrahierte Daten
        if "extracted_data" in ai_decision:
            self._update_session_data(session, ai_decision["extracted_data"])
        
        # AI generiert supportiven Abschluss
        closing = self._generate_closing(session)
        self.bot.send_message(phone_number, closing)
        
        # Points vergeben
        points = ai_decision.get("points", 2)
        
        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(points, self.bot)
        
        # Daten speichern
        self._save_session_data(phone_number, session, points)
        
        # Cleanup
        if self.study_manager:

            pass  # advance_day disabled - day advances by real time only

        

        del self.sessions[phone_number]
        logger.info(f"Maintenance completed early for {phone_number}: {points} points")
    
    def _extract_final_data(self, session: Dict, text: str):
        """Versucht aus letzter Antwort noch Daten zu extrahieren"""
        current_step = session["step"]
        data = session["data"]
        
        # Nur extrahieren wenn nicht "nichts"
        nothing_signals = ["nichts", "weiß nicht", "keine ahnung", "fällt mir nicht ein"]
        if not any(signal in text.lower() for signal in nothing_signals):
            if current_step == 1 and len(text) > 15:
                # Erfolg
                data["successes"].append(text[:200])
            elif current_step == 2 and len(text) > 15:
                # Schwerer Moment
                data["challenges"].append(text[:200])
            elif current_step == 3 and len(text) > 15:
                # Tipp/Strategie
                data["tips"].append(text[:200])
    
    def _generate_closing(self, session: Dict) -> str:
        """AI generiert supportiven Abschluss mit Fokus auf Offenheit"""
        
        conversation = self._format_conversation(session["conversation"])
        data = session["data"]
        had_nothing = session.get("had_nothing", False)
        
        prompt = f"""Erstelle einen kurzen, supportiven Abschluss für diese Maintenance-Intervention zu OFFENHEIT.

TECHNIKEN:
- Peer Support: Supportiv, nicht belehrend
- Ressourcenaktivierung: Stärken bei OFFENHEIT würdigen
- Selbstmanagement: User ist selbst kompetent
- NICHT missionarisch!

KONTEXT:
- User hatte teilweise "nichts" zu berichten: {had_nothing}
- Fokus war OFFENHEIT FÜR ANDERE MEINUNGEN

GESAMMELTE DATEN:
- Erfolge mit Offenheit: {data.get('successes', [])}
- Schwere Momente: {data.get('challenges', [])}
- Tipps für Offenheit: {data.get('tips', [])}

DIALOG:
{conversation}

ANFORDERUNGEN:
- 2-3 Sätze maximum
- Würdige Check-in (auch wenn User wenig teilte!)
- Fokus: OFFENHEIT FÜR ANDERE MEINUNGEN
- Zeige, dass Schwierigkeiten mit Offenheit normal sind
- Motiviere SUBTIL (nicht missionarisch!)
- Peer Support Ton: "Gut, dass du dich damit beschäftigst"
- Jugendgerecht (11-25 Jahre)

WICHTIG:
- NIEMALS "Schule/Studium/Klasse"
- Keine übertriebenen Lobpreisungen
- Supportiv, nicht direktiv
- Wenn User "nichts" hatte → trotzdem wertschätzen!

BEISPIEL-STILE:

Wenn User teilte:
"Cool, dass du reflektierst wie's mit Offenheit läuft! Schwierige Momente gehören dazu. Bleib dran! 💪"

Wenn User wenig teilte:
"Danke fürs Check-in! Manchmal ist's schwer konkrete Situationen zu nennen - alles gut. Schön, dass du dir Zeit nimmst! 💪"

Antworte NUR mit der Abschlussnachricht, kein JSON."""
        
        result = self.ai._make_request(prompt, max_tokens=150, temperature=0.8)
        return result or "Super, dass du reflektierst! Bleib dran - du machst das gut! 💪"
    
    def _emergency_complete(self, phone_number: str):
        """Notfall-Abschluss bei Fehler"""
        self.bot.send_message(
            phone_number,
            "Danke fürs Check-in zu Offenheit! Bleib dran! 💪"
        )
        
        if phone_number in self.sessions:
            session = self.sessions[phone_number]
            self._save_session_data(phone_number, session, points=1, error=True)
            if self.study_manager:

                pass  # advance_day disabled - day advances by real time only

            

            del self.sessions[phone_number]
    
    # ===== HELPER METHODS =====
    
    def _add_to_conversation(self, phone_number: str, role: str, content: str):
        """Fügt Message zur Conversation hinzu"""
        self.sessions[phone_number]["conversation"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def _format_conversation(self, conversation: list) -> str:
        """Formatiert für AI-Prompts"""
        formatted = []
        for msg in conversation[-10:]:  # Letzte 10 Messages
            role = "ELLA" if msg["role"] == "assistant" else "User"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)
    
    def _update_session_data(self, session: Dict, extracted_data: Dict):
        """Updated Session-Daten mit extrahierten Informationen"""
        data = session.get("data", {})
        
        if extracted_data.get("successes"):
            data["successes"].extend(extracted_data["successes"])
        if extracted_data.get("challenges"):
            data["challenges"].extend(extracted_data["challenges"])
        if extracted_data.get("tips"):
            data["tips"].extend(extracted_data["tips"])
        if extracted_data.get("strategies"):
            data["strategies"].extend(extracted_data["strategies"])
        
        session["data"] = data
    
    def _parse_json(self, response: str, fallback: Dict) -> Dict:
        """Parse JSON mit Fallback"""
        try:
            if "{" in response and "}" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
                return json.loads(json_str)
        except Exception as e:
            logger.warning(f"JSON parse failed in Maintenance: {e}")
        return fallback
    
    def _save_session_data(self, phone_number: str, session: Dict, points: int, error: bool = False):
        """Speichert Session-Daten für Analyse"""
        try:
            filepath = "../data/maintenance_ai_sessions_v2.1.jsonl"
            
            with open(filepath, "a", encoding="utf-8") as f:
                data = {
                    "timestamp": datetime.now().isoformat(),
                    "phone_number": phone_number,
                    "phase": "Maintenance",
                    "version": "v2.1_openness_focus",
                    "duration_seconds": (
                        datetime.now() - datetime.fromisoformat(session["start_time"])
                    ).total_seconds(),
                    "final_step": session["step"],
                    "interaction_count": session["interaction_count"],
                    "had_nothing": session.get("had_nothing", False),
                    "points_awarded": points,
                    "conversation": session["conversation"],
                    "collected_data": session["data"],
                    "user_state": session["user_state_snapshot"],
                    "error": error
                }
                
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"Error saving Maintenance data: {e}")
    
    # ===== STATUS METHODS =====
    
    def is_active(self, phone_number: str) -> bool:
        """Prüft ob aktiv"""
        return phone_number in self.sessions
    
    def get_active_users(self) -> list:
        """Liste aktiver User"""
        return list(self.sessions.keys())
    
    def get_session_info(self, phone_number: str) -> Optional[Dict]:
        """Session-Info"""
        return self.sessions.get(phone_number)
    
    def _cleanup_state(self, phone_number: str):
        """Cleanup method for intervention manager"""
        if phone_number in self.sessions:
            if self.study_manager:

                pass  # advance_day disabled - day advances by real time only

            

            del self.sessions[phone_number]


# ===== TEST =====

if __name__ == "__main__":
    """Test mit "nichts eingefallen" Handling"""
    
    class MockBot:
        def send_message(self, recipient, message):
            print(f"\n📱 → {recipient[:20]}...")
            print(f"💬 {message}\n")
    
    handler = AIMaintenanceHandler(MockBot())
    test_user = "+491234567890"
    
    print("=" * 70)
    print("TEST: Maintenance Handler v2.1 - 'NICHTS EINGEFALLEN' HANDLING")
    print("=" * 70)
    
    # Start
    print("\n1️⃣ ELLA startet Check-in zu OFFENHEIT...")
    handler.start_intervention(test_user)
    
    # Interaktion 1: User hat NICHTS
    print("\n2️⃣ USER Interaktion 1/3: Sagt 'nichts'")
    handler.handle_message(
        test_user, 
        "Hab gerade keine Situation"
    )
    
    # Interaktion 2: User hat wieder NICHTS
    print("\n3️⃣ USER Interaktion 2/3: Wieder 'nichts'")
    handler.handle_message(
        test_user,
        "Weiß nicht, fällt mir nichts ein"
    )
    
    # Interaktion 3: User gibt doch Tipp (FINALE)
    print("\n4️⃣ USER Interaktion 3/3: Gibt Tipp (FINALE)")
    handler.handle_message(
        test_user,
        "Vielleicht erstmal tief durchatmen"
    )
    
    print("\n✅ Test complete - auch mit 'nichts' funktioniert's!")
    print("📊 Check ../data/maintenance_ai_sessions_v2.1.jsonl für Details")
