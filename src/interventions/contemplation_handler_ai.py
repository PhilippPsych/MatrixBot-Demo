#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Powered Contemplation Handler v2
Max. 3 Interaktionen - Narrative & personzentrierte Ansätze
"""

import logging
import json
from typing import Dict, Optional
from datetime import datetime
from ai_service import AIService
from user_state_points import UserState

logger = logging.getLogger(__name__)


class AIContemplationHandler:
    """
    AI-gesteuerter Contemplation Handler mit narrativen Ansätzen
    
    Phase-Ziel: Ambivalenz erkunden (weniger direktiv)
    
    Techniken:
    - Narrative Ansätze (Storytelling)
    - Ressourcenaktivierung
    - Personzentrierte Gesprächsführung (statt direktive Führung)
    - Achtsamkeitsbasierte Selbstreflexion
    
    Interventionstypen:
    - Situationen erzählen (eigene Erfahrungen)
    - Geschichten lesen (und reflektieren)
    - Erfahrungen teilen (verschiedene Perspektiven)
    
    Struktur (max. 3 Interaktionen):
    1. Opening: Einladung zum Teilen einer Situation/Geschichte
    2. Vertiefung: Eine empathische, nicht-direktive Nachfrage
    3. Abschluss: Würdigung der Reflexion
    """
    
    MAX_INTERACTIONS = 3  # Harte Grenze
    
    def __init__(self, bot_instance, study_manager=None):
        self.bot = bot_instance
        self.study_manager = study_manager
        self.ai = AIService()
        self.sessions: Dict[str, Dict] = {}
    
    def start_intervention(self, phone_number: str) -> bool:
        """AI wählt narrative Intervention und startet mit max 3 Interaktionen"""
        if phone_number in self.sessions:
            logger.warning(f"Contemplation already active for {phone_number}")
            return False
        
        # Lade User-State für Kontext
        user_state = UserState.load(phone_number)
        
        # AI wählt beste Intervention
        intervention = self._ai_select_intervention(phone_number, user_state)
        
        # Initialisiere Session mit Interaktionszähler
        self.sessions[phone_number] = {
            "type": intervention["type"],
            "start_time": datetime.now().isoformat(),
            "conversation": [],
            "interaction_count": 0,
            "user_state_snapshot": {
                "level": user_state.level,
                "points": user_state.engagement_points,
                "total_interventions": user_state.total_interventions
            }
        }
        
        # Sende Eröffnung
        self.bot.send_message(phone_number, intervention["opening_message"])
        
        # Speichere in Conversation History
        self._add_to_conversation(phone_number, "assistant", intervention["opening_message"])
        
        return True
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """AI verarbeitet Antwort mit striktem Interaktions-Limit"""
        if phone_number not in self.sessions:
            return False
        
        session = self.sessions[phone_number]
        
        # Inkrementiere Interaktionszähler
        session["interaction_count"] += 1
        
        # Füge User-Antwort zur History hinzu
        self._add_to_conversation(phone_number, "user", text)
        
        try:
            # Prüfe Interaktions-Limit
            if session["interaction_count"] >= self.MAX_INTERACTIONS:
                # Letzte Interaktion - muss abschließen
                self._force_complete_intervention(phone_number)
                return True
            
            # AI analysiert Antwort und entscheidet über nächsten Schritt
            ai_decision = self._ai_process_response(phone_number, text, session)
            
            # Handle basierend auf AI-Entscheidung
            if ai_decision["action"] == "continue":
                # Eine letzte Vertiefung (nur möglich bei Interaktion 1)
                self.bot.send_message(phone_number, ai_decision["message"])
                self._add_to_conversation(phone_number, "assistant", ai_decision["message"])
                
            elif ai_decision["action"] == "complete":
                # Vorzeitiger Abschluss
                self._complete_intervention(phone_number, ai_decision)
            
            elif ai_decision["action"] == "redirect":
                # User benötigt andere Intervention
                self._redirect_intervention(phone_number, ai_decision)
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing message in Contemplation: {e}")
            self._emergency_complete(phone_number)
            return False
    
    def _ai_select_intervention(self, phone_number: str, user_state: UserState) -> Dict:
        """AI wählt beste narrative Contemplation-Intervention"""
        prompt = f"""Du bist ELLA, ein Coach für Jugendliche und junge Erwachsene (11-25 Jahre).
Wähle die beste Contemplation-Intervention mit narrativen Ansätzen.

ZIEL:
Ambivalenz erkunden - weniger direktiv, mehr narrativ und personzentriert

USER-PROFIL:
- Level: {user_state.level}
- Punkte: {user_state.engagement_points}
- Bisherige Interventionen: {user_state.total_interventions}
- Phase: Contemplation (ambivalent über Offenheit gegenüber anderen Meinungen)

VERFÜGBARE INTERVENTIONS-TYPEN:

1. **situation_reflection** (Situationen erzählen)
   - User teilt eigene Erfahrung mit schwierigen Diskussionen
   - Narrativer Ansatz: Storytelling aus eigenem Leben
   - Achtsamkeit: Was ist passiert? Wie hat es sich angefühlt?

2. **story_discussion** (Geschichten lesen)
   - User liest kurze Geschichte über Meinungsverschiedenheit
   - Narrativer Ansatz: Perspektivenwechsel durch Geschichte
   - Ressourcenaktivierung: Eigene Interpretation finden

3. **emotion_exploration** (Erfahrungen teilen)
   - User erkundet eigene Gefühle bei Meinungsverschiedenheiten
   - Personzentriert: Gefühle als Ressource, nicht als Problem
   - Achtsamkeitsbasiert: Innere Reaktionen wahrnehmen

4. **perspective_shift** (Erfahrungen teilen)
   - User überlegt, warum Menschen unterschiedlich denken
   - Narrativer Ansatz: Geschichten anderer nachvollziehen
   - Ressourcenaktivierung: Neugier statt Bewertung

TECHNIKEN ZU VERWENDEN:
- Narrativ: Geschichten statt Argumente
- Personzentriert: Validierung statt Korrektur
- Ressourcenaktivierung: Stärken betonen
- Achtsamkeit: Wahrnehmen ohne Bewerten

AUFGABE:
Wähle den besten Typ und formuliere eine einladende, nicht-direktive Eröffnungsnachricht (1-2 Sätze).

WICHTIG:
- Jugendgerecht (11-25 Jahre)
- Nicht belehrend, sondern neugierig und empathisch
- Konkrete Beispiele oder kleine Geschichte anbieten
- Keine offenen "Warum?"-Fragen, sondern Wahlmöglichkeiten
- NIEMALS "Schule/Studium/Klasse" - stattdessen: "beim Lernen", "im Alltag", "in Gruppen"

ANTWORT-FORMAT (JSON):
{{
    "type": "situation_reflection|story_discussion|emotion_exploration|perspective_shift",
    "opening_message": "Deine einladende, narrative Eröffnungsnachricht",
    "rationale": "Warum dieser Typ für diesen User?"
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=300, temperature=0.8)
        return self._parse_json(response, {
            "type": "situation_reflection",
            "opening_message": "Manchmal haben wir verschiedene Gefühle bei Diskussionen... Magst du von einer Situation erzählen, wo du nicht genau wusstest, was du denken sollst?",
        })
    
    def _ai_process_response(self, phone_number: str, text: str, session: Dict) -> Dict:
        """AI analysiert User-Antwort mit personzentriertem, nicht-direktivem Ansatz"""
        
        conversation_context = self._format_conversation(session["conversation"])
        interaction_count = session["interaction_count"]
        remaining = self.MAX_INTERACTIONS - interaction_count
        
        prompt = f"""Du bist ELLA in einer Contemplation-Intervention mit narrativen Ansätzen.

**HARTER LIMIT: Nur noch {remaining} ELLA-Antworten möglich!**

TECHNIKEN:
- Narrativ (Storytelling, Geschichten)
- Personzentriert (Validierung, keine Korrektur)
- Ressourcenaktivierung (Stärken betonen)
- Achtsamkeit (Wahrnehmen ohne Bewerten)

ZIEL:
Ambivalenz erkunden - NICHT direktiv führen, sondern Raum für Reflexion geben

INTERVENTION-TYP: {session["type"]}
INTERAKTION: {interaction_count}/{self.MAX_INTERACTIONS}

BISHERIGER DIALOG:
{conversation_context}

USER HAT GERADE GEANTWORTET: "{text}"

**ENTSCHEIDUNGSLOGIK - STRIKT NACH INTERAKTIONSZAHL:**

**Interaktion 1 (gerade passiert):**
- Wenn User Situation/Geschichte geteilt hat → CONTINUE mit EINER empathischen, nicht-direktiven Vertiefungsfrage
- Wenn User ausweicht oder sehr oberflächlich → CONTINUE mit sanfter Einladung (konkretes Beispiel geben)
- Wenn User bereits substantiell reflektiert → COMPLETE (nicht künstlich verlängern!)

**Interaktion 2 (gerade passiert):**
- Wenn User gut reflektiert → COMPLETE (Ziel erreicht!)
- Wenn User blockiert wirkt → REDIRECT (andere Intervention)
- Wenn sehr kurze Antwort → CONTINUE mit letzter, sehr konkreter Frage

**Interaktion 3 (LETZTE - gerade passiert):**
- IMMER COMPLETE
- Würdige was User geteilt hat
- Ambivalenz als wertvoll darstellen

WICHTIG FÜR CONTINUE (nur Interaktion 1-2):
- Personzentriert: "Wie war das für dich?" statt "Warum hast du...?"
- Narrativ: Baue auf die Geschichte des Users auf
- Achtsamkeit: "Was hast du bemerkt?" "Wie hat es sich angefühlt?"
- Ressourcen: "Was hat dir geholfen?" "Was war stark an dir?"
- 1-2 Sätze maximum
- Empathisch, nicht bewertend
- NIEMALS "Schule/Studium/Klasse"

LERNZIEL ERREICHT WENN:
- User hat Ambivalenz erkundet (verschiedene Gefühle/Perspektiven gesehen)
- Natürlicher Gesprächsabschluss
- User zeigt Reflexion (nicht nur oberflächliche Antworten)

ANTWORT (JSON):
{{
    "action": "continue|complete|redirect",
    "message": "Deine empathische Nachfrage (nur bei continue, 1-2 Sätze)",
    "points": 1-3,
    "completion_note": "Was User reflektiert hat (nur bei complete)",
    "reasoning": "Kurze Begründung"
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=300, temperature=0.8)
        return self._parse_json(response, {
            "action": "complete",
            "message": "",
            "points": 1,
            "reasoning": "fallback"
        })
    
    def _force_complete_intervention(self, phone_number: str):
        """Erzwingt Abschluss nach 3. Interaktion"""
        session = self.sessions[phone_number]
        
        # Generiere empathischen Abschluss
        closing = self._ai_generate_closing(phone_number, session)
        self.bot.send_message(phone_number, closing)
        
        # Points vergeben
        points = 2  # Standard bei 3 Interaktionen
        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(points, self.bot)
        
        # Speichere Daten
        self._save_session_data(phone_number, session, points)
        
        if self.study_manager:
            pass  # advance_day disabled - day advances by real time only

        # Cleanup
        del self.sessions[phone_number]
        
        logger.info(f"Contemplation force-completed for {phone_number}: {points} points")
    
    def _complete_intervention(self, phone_number: str, ai_decision: Dict):
        """Schließt Intervention vorzeitig ab (User hat gut reflektiert)"""
        session = self.sessions[phone_number]
        
        # Vergebe Punkte
        points = ai_decision.get("points", 2)
        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(points, self.bot)
        
        # AI-generierte Abschlussnachricht
        closing = self._ai_generate_closing(phone_number, session)
        self.bot.send_message(phone_number, closing)
        
        # Speichere Daten
        self._save_session_data(phone_number, session, points)
        
        if self.study_manager:
            pass  # advance_day disabled - day advances by real time only

        # Cleanup
        del self.sessions[phone_number]
        
        logger.info(f"Contemplation completed early for {phone_number}: {points} points")
    
    def _ai_generate_closing(self, phone_number: str, session: Dict) -> str:
        """AI generiert empathischen, nicht-direktiven Abschluss"""
        conversation = self._format_conversation(session["conversation"])
        
        prompt = f"""Du bist ELLA. Formuliere einen kurzen, personzentrierten Abschluss dieser Contemplation-Intervention.

TECHNIKEN:
- Personzentriert: Validierung statt Lob
- Narrativ: Würdige die geteilte Geschichte
- Ressourcenaktivierung: Zeige was User bereits hat
- Achtsamkeit: Ambivalenz als wertvoll darstellen

INTERVENTION-TYP: {session["type"]}

DIALOG:
{conversation}

ANFORDERUNGEN:
- 1-2 Sätze
- Würdige die Reflexion des Users (nicht "Super gemacht!", sondern echte Wertschätzung)
- Zeige, dass Ambivalenz und gemischte Gefühle normal und wertvoll sind
- Motiviere SUBTIL zur Offenheit (nicht belehrend!)
- Jugendgerecht (11-25 Jahre)
- NIEMALS "Schule/Studium/Klasse"

BEISPIEL-STILE (personzentriert, nicht direktiv):
- "Danke, dass du deine Erfahrung geteilt hast. Es ist völlig okay, manchmal unterschiedliche Gefühle zu haben."
- "Schön, dass du dir Zeit zum Nachdenken genommen hast. Ambivalenz zu spüren zeigt, dass du verschiedene Seiten siehst."
- "Danke für deine Offenheit. Es ist wertvoll, wenn wir bemerken, wie komplex manche Situationen sind."

Antworte NUR mit der Abschlussnachricht, kein JSON."""
        
        response = self.ai._make_request(prompt, max_tokens=150, temperature=0.8)
        return response or "Danke für deine Gedanken! Es ist okay, manchmal unsicher zu sein. 💭"
    
    def _redirect_intervention(self, phone_number: str, ai_decision: Dict):
        """Leitet auf andere Intervention um (User ist blockiert)"""
        # Graceful Exit mit Validierung
        self.bot.send_message(
            phone_number,
            "Danke für deine Offenheit! Manchmal braucht's Zeit, um über sowas nachzudenken. 💭"
        )
        
        session = self.sessions[phone_number]
        self._save_session_data(phone_number, session, points=1)
        if self.study_manager:
            pass  # advance_day disabled - day advances by real time only
        del self.sessions[phone_number]
    
    def _emergency_complete(self, phone_number: str):
        """Notfall-Abschluss bei Fehler"""
        self.bot.send_message(
            phone_number,
            "Danke für deine Teilnahme! 💭"
        )
        
        if phone_number in self.sessions:
            session = self.sessions[phone_number]
            self._save_session_data(phone_number, session, points=1, error=True)
            
            if self.study_manager:
                pass  # advance_day disabled - day advances by real time only
            
            del self.sessions[phone_number]
    
    # ===== HELPER METHODS =====
    
    def _add_to_conversation(self, phone_number: str, role: str, content: str):
        """Fügt Message zur Conversation History hinzu"""
        self.sessions[phone_number]["conversation"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def _format_conversation(self, conversation: list) -> str:
        """Formatiert Conversation für AI-Prompts"""
        formatted = []
        for msg in conversation:
            role = "ELLA" if msg["role"] == "assistant" else "User"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)
    
    def _parse_json(self, response: str, fallback: Dict) -> Dict:
        """Parse JSON aus AI-Response mit Fallback"""
        try:
            # Finde JSON in Response
            if "{" in response and "}" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
                return json.loads(json_str)
        except Exception as e:
            logger.warning(f"Failed to parse AI JSON: {e}")
        
        return fallback
    
    def _save_session_data(self, phone_number: str, session: Dict, points: int, error: bool = False):
        """Speichert Session-Daten für Analyse"""
        try:
            filepath = "../data/contemplation_ai_sessions_v2.jsonl"
            
            with open(filepath, "a", encoding="utf-8") as f:
                data = {
                    "timestamp": datetime.now().isoformat(),
                    "phone_number": phone_number,
                    "intervention_type": session["type"],
                    "version": "v2_max3",
                    "duration_seconds": (
                        datetime.now() - datetime.fromisoformat(session["start_time"])
                    ).total_seconds(),
                    "interaction_count": session["interaction_count"],
                    "points_awarded": points,
                    "conversation": session["conversation"],
                    "user_state": session["user_state_snapshot"],
                    "error": error
                }
                
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"Error saving session data: {e}")
    
    # ===== STATUS METHODS =====
    
    def is_active(self, phone_number: str) -> bool:
        """Prüft ob Intervention aktiv"""
        return phone_number in self.sessions
    
    def get_active_users(self) -> list:
        """Liste aktiver User"""
        return list(self.sessions.keys())
    
    def get_session_info(self, phone_number: str) -> Optional[Dict]:
        """Info über aktive Session"""
        return self.sessions.get(phone_number)


# ===== BEISPIEL-USAGE =====

if __name__ == "__main__":
    """Test mit max 3 Interaktionen"""
    
    # Mock Bot
    class MockBot:
        def send_message(self, recipient, message):
            print(f"\n📱 → {recipient[:20]}...")
            print(f"💬 {message}\n")
    
    # Test
    handler = AIContemplationHandler(MockBot())
    
    test_user = "+491234567890"
    
    print("=" * 70)
    print("TEST: Contemplation Handler v2 (MAX 3 INTERAKTIONEN)")
    print("=" * 70)
    
    # Start Intervention
    print("\n1️⃣ ELLA startet Intervention...")
    handler.start_intervention(test_user)
    
    # Interaktion 1
    print("\n2️⃣ USER Interaktion 1/3: Teilt Situation")
    handler.handle_message(
        test_user, 
        "Letztens beim Lernen mit Freunden ging's um Klimaschutz. Alle hatten krass unterschiedliche Meinungen."
    )
    
    # Interaktion 2
    print("\n3️⃣ USER Interaktion 2/3: Vertieft")
    handler.handle_message(
        test_user,
        "Ich wusste nicht was ich sagen soll. Die einen fanden Demos wichtig, die anderen nervig. Beide hatten irgendwie Recht."
    )
    
    # Interaktion 3 - LETZTE
    print("\n4️⃣ USER Interaktion 3/3: Letzte Antwort (FINALE)")
    handler.handle_message(
        test_user,
        "War komisch, weil ich beide Seiten verstehen konnte. Fühlt sich manchmal an wie man sich nicht entscheiden kann."
    )
    
    print("\n✅ Test complete - genau 3 Interaktionen!")
