#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Powered Preparation Handler v2.0 - IMPROVED
Drei Modi mit klar definierten therapeutischen Techniken

IMPROVEMENTS:
- Alle Modi auf max 3 Interaktionen reduziert
- Therapeutische Techniken klar definiert und dokumentiert
- Konkretere Fragen mit Beispielen
- Validierung + Frage Struktur
"""

import logging
import json
from typing import Dict, Optional
from datetime import datetime
from ai_service import AIService
from user_state_points import UserState

logger = logging.getLogger(__name__)


class AIPreparationHandler:
    """
    AI-gesteuerter Preparation Handler - Phase: Vorbereitung zur Handlung
    
    ZIEL: User bereitet sich aktiv auf Handlung vor
    
    DREI MODI MIT THERAPEUTISCHEN TECHNIKEN (MAX 3 INTERAKTIONEN):
    
    1. **action_planning** (3 Steps)
       Therapeutische Technik: Problemlösetraining + Implementation Intentions
       - User entwickelt konkreten WANN-WO-WIE Plan
       - Implementation Intentions: "Wenn Situation X, dann tue ich Y"
       - Selbstwirksamkeit stärken durch konkrete Pläne
       Referenz: Gollwitzer (1999) - Implementation Intentions
       
    2. **barrier_identification** (3 Steps)
       Therapeutische Technik: Problemlösetraining + Coping-Strategien
       - User identifiziert mögliche Hindernisse
       - Entwickelt konkrete Strategien für Hindernisse
       - Mentale Vorbereitung auf Schwierigkeiten
       Referenz: D'Zurilla & Nezu - Problem-Solving Therapy
       
    3. **skill_practice** (3 Steps)
       Therapeutische Technik: Rollenspiel + Exposition in sensu (imaginativ)
       - User übt in simuliertem Dialog
       - Mentale Durchführung schwieriger Situationen
       - Verhaltensrepertoire erweitern
       Referenz: Verhaltenstherapie - Behavioral Rehearsal
    """
    
    MAX_STEPS = 3  # ALLE MODI
    
    def __init__(self, bot_instance, study_manager=None):
        self.bot = bot_instance
        self.study_manager = study_manager
        self.ai = AIService()
        self.sessions: Dict[str, Dict] = {}
    
    def start_intervention(self, phone_number: str) -> bool:
        """AI wählt Modus und startet Intervention"""
        if phone_number in self.sessions:
            logger.warning(f"Preparation already active for {phone_number}")
            return False
        
        user_state = UserState.load(phone_number)
        
        # AI wählt besten Modus
        intervention = self._ai_select_mode(user_state)
        mode = intervention["mode"]
        
        # Initialisiere Session
        self.sessions[phone_number] = {
            "mode": mode,  # action_planning, barrier_identification, skill_practice
            "start_time": datetime.now().isoformat(),
            "conversation": [],
            "step": 1,
            "max_steps": self.MAX_STEPS,  # IMMER 3
            "data": {
                "plan": None,
                "barriers": [],
                "strategies": [],
                "dialog_practice": None
            },
            "user_state_snapshot": {
                "level": user_state.level,
                "points": user_state.engagement_points
            }
        }
        
        # Sende Opening
        opening = intervention["opening_message"]
        self.bot.send_message(phone_number, opening)
        self._add_to_conversation(phone_number, "assistant", opening)
        
        logger.info(f"Preparation started: mode={mode}, max_steps=3")
        
        return True
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Verarbeitet Antwort basierend auf Modus"""
        if phone_number not in self.sessions:
            return False
        
        session = self.sessions[phone_number]
        mode = session["mode"]
        self._add_to_conversation(phone_number, "user", text)
        
        # KRITISCH: Step-Limit Check
        if session["step"] >= session["max_steps"]:
            logger.info(f"Preparation: Force complete at step {session['step']} (mode: {mode})")
            self._force_complete(phone_number, session)
            return True
        
        # Prüfe auf "weiß nicht" / unsichere Antworten
        if self._is_uncertain_response(text):
            return self._handle_uncertain_response(phone_number, text, session)
        
        try:
            # Modus-spezifische Verarbeitung
            if mode == "action_planning":
                return self._handle_action_planning(phone_number, text, session)
            elif mode == "barrier_identification":
                return self._handle_barrier_identification(phone_number, text, session)
            elif mode == "skill_practice":
                return self._handle_skill_practice(phone_number, text, session)
            else:
                # Fallback
                return self._handle_generic(phone_number, text, session)
                
        except Exception as e:
            logger.error(f"Error in Preparation ({mode}): {e}")
            self._emergency_complete(phone_number)
            return False
    
    def _is_uncertain_response(self, text: str) -> bool:
        """Erkennt unsichere/unklare Antworten"""
        uncertain_patterns = [
            "weiß nicht", "keine ahnung", "bin mir unsicher",
            "nicht sicher", "fällt mir nichts ein", "hm", "hmm",
            "öhm", "ähm", "k.a.", "ka", "keine idee"
        ]
        text_lower = text.lower().strip()
        return any(pattern in text_lower for pattern in uncertain_patterns) or len(text_lower) < 5
    
    def _handle_uncertain_response(self, phone_number: str, text: str, session: Dict) -> bool:
        """Bietet Wahlmöglichkeiten bei unsicheren Antworten"""
        mode = session["mode"]
        step = session["step"]
        
        examples = self._get_examples_for_mode(mode, step)
        
        prompt = f"""Du bist ELLA. User sagte: "{text}" (wirkt unsicher).

MODUS: {mode}
STEP: {step} von 3

Biete 2-3 KONKRETE Wahlmöglichkeiten als Inspiration.

{examples}

FORMAT:
"Kein Problem! Hier ein paar Ideen:

• [Beispiel 1]
• [Beispiel 2]
• [Beispiel 3]

Was passt am besten? Oder war's was anderes?"

WICHTIG:
- Konkrete, altersgerechte Beispiele (11-25 Jahre)
- Flexibler Kontext (nicht "Schule")
- Max 4 Sätze
"""
        
        response = self.ai._make_request(prompt, max_tokens=250, temperature=0.8)
        
        if response:
            self.bot.send_message(phone_number, response)
            self._add_to_conversation(phone_number, "assistant", response)
            return True
        else:
            return self._continue_conversation(phone_number, session)
    
    def _get_examples_for_mode(self, mode: str, step: int) -> str:
        """Gibt Beispiele für Modi und Steps zurück"""
        
        if mode == "action_planning":
            return """BEISPIELE für konkrete Pläne:
• "Wenn jemand beim nächsten Treffen was Kontroverses sagt, frage ich nach Gründen"
• "Nächste Woche im Gruppenprojekt höre ich erstmal allen zu"
• "Beim nächsten Familienessen frage ich aktiv nach anderen Meinungen"""
        
        elif mode == "barrier_identification":
            if step == 1:
                return """BEISPIELE für Hindernisse:
• Andere könnten genervt reagieren
• Ich könnte emotional werden
• Diskussion könnte eskalieren
• Zeitdruck/Stress könnte mich ablenken"""
            else:
                return """BEISPIELE für Strategien:
• Tief durchatmen bevor ich antworte
• Ruhig nachfragen: "Wie meinst du das?"
• Pause machen wenn's zu heftig wird
• Mir vorher überlegen was ich sagen will"""
        
        elif mode == "skill_practice":
            return """BEISPIELE für offene Reaktionen:
• "Interessant! Wie kommst du darauf?"
• "Erzähl mal mehr - was ist deine Erfahrung?"
• "Verstehe deinen Punkt. Ich sehe das etwas anders, weil..."
• "Da hab ich noch nicht drüber nachgedacht. Was spricht dafür?"""
        
        return ""
    
    def _ai_select_mode(self, user_state: UserState) -> Dict:
        """AI wählt besten Modus für User"""
        
        prompt = f"""Du bist ELLA. Wähle den besten Preparation-Modus für User Level {user_state.level}.

DREI MODI (ALLE MAX 3 STEPS):

1. **action_planning** (Problemlösetraining + Implementation Intentions)
   - User entwickelt konkreten WANN-WO-WIE Plan
   - Implementation Intentions: "Wenn X, dann tue ich Y"
   - Fokus: Konkrete Handlungsschritte planen
   
2. **barrier_identification** (Problemlösetraining + Coping-Strategien)
   - User identifiziert mögliche Hindernisse
   - Entwickelt konkrete Strategien für Hindernisse
   - Fokus: Vorbereitung auf Schwierigkeiten

3. **skill_practice** (Rollenspiel + Exposition in sensu)
   - User übt in simuliertem Dialog
   - Mentale Durchführung schwieriger Situationen
   - Fokus: Kommunikations-Skills trainieren

WÄHLE basierend auf:
- Level 1-2: eher action_planning (einfacher, konkreter)
- Level 3-4: barrier_identification oder skill_practice
- Alle 3-4 Interventionen: skill_practice (wichtig für Übung!)

ZIELGRUPPE: Junge Menschen (11-25 Jahre)
- Schüler, Studenten, Azubis
- NIEMALS "Schule" sagen - stattdessen: "beim Lernen", "in Gruppen", "im Alltag"

OPENING MESSAGE:
- Kurz (2-3 Sätze)
- KONKRET mit Beispiel
- Passend zum Modus
- Aktivierend, mit Frage am Ende

JSON:
{{
    "mode": "action_planning|barrier_identification|skill_practice",
    "opening_message": "Deine Eröffnung MIT konkretem Beispiel und Frage",
    "rationale": "Warum dieser Modus?"
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=300, temperature=0.8)
        result = self._parse_json(response, {
            "mode": "action_planning",
            "opening_message": "Zeit für konkrete Pläne! 💪\n\nStell dir vor, du bist beim nächsten Mal in einer Diskussion. Was willst du dann anders machen?",
            "rationale": "fallback"
        })
        
        logger.info(f"AI selected mode: {result['mode']} ({result.get('rationale', 'no rationale')})")
        return result
    
    # ===== MODUS 1: ACTION PLANNING =====
    
    def _handle_action_planning(self, phone_number: str, text: str, session: Dict) -> bool:
        """Modus 1: Konkreten Handlungsplan entwickeln (Implementation Intentions) - MAX 3 STEPS"""
        
        conversation = self._format_conversation(session["conversation"])
        step = session["step"]
        
        prompt = f"""Du bist ELLA in Action Planning (Implementation Intentions).

THERAPEUTISCHE TECHNIK: Implementation Intentions (Gollwitzer, 1999)
- "Wenn Situation X, dann tue ich Y"
- Konkrete Pläne erhöhen Handlungswahrscheinlichkeit
- WANN + WO + WIE definieren

ZIEL: User entwickelt KONKRETEN Plan
- WANN will ich handeln?
- WO genau?
- WIE konkret?

STEP: {step} von 3

DIALOG:
{conversation}

USER: "{text}"

FLOW:
1. User nennt grobe Idee → Frage: "Wann und wo genau?" MIT Beispielen
2. User konkretisiert → Frage: "Wie genau willst du das sagen/tun?" MIT Beispielen
3. Abschluss → complete!

FRAGEN MIT BEISPIELEN:

Step 1 → 2:
"Gute Idee! ✅ Wann und wo genau willst du das probieren? Zum Beispiel:
• Beim nächsten Gruppentreffen am [Tag]
• Nächste Woche wenn wir [Aktivität] machen
• Beim nächsten Mal wenn [Situation] kommt"

Step 2 → 3:
"Super! ✅ Wie genau willst du reagieren? Zum Beispiel:
• 'Interessant! Wie kommst du darauf?'
• 'Erzähl mehr - was ist deine Erfahrung?'
• 'Da hab ich noch nicht drüber nachgedacht...'"

WICHTIG:
- BIAS zu "complete" ab Step 2
- Kurze Nachrichten (max 3 Sätze)
- IMMER Validierung + konkrete Frage mit Beispielen
- Selbstwirksamkeit fördern: "Du schaffst das!"
- NIEMALS "Schule" - stattdessen: "beim Lernen", "in Gruppen"

ENTSCHEIDUNG:
- Step 2+: Starke Tendenz zu complete
- Step 3: IMMER complete

JSON:
{{
    "action": "continue|complete",
    "message": "VALIDIERUNG + KONKRETE FRAGE mit Beispielen (wenn continue)",
    "plan_details": {{
        "plan": "Was will User tun?",
        "when_where": "Wann/wo?",
        "how": "Wie genau?"
    }},
    "points": 1-2
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=350, temperature=0.8)
        decision = self._parse_json(response, {"action": "complete", "points": 1})
        
        # Update Data
        if decision.get("plan_details"):
            for key, value in decision["plan_details"].items():
                if value:
                    session["data"][key] = value
        
        # Safety Check: Ab Step 2 → complete bias
        if step >= 2:
            decision["action"] = "complete"
        
        # Quality Check
        if decision["action"] == "continue":
            message = decision.get("message", "")
            if not message or "?" not in message:
                logger.warning("AI response missing question mark, forcing complete")
                decision["action"] = "complete"
        
        if decision["action"] == "continue":
            self.bot.send_message(phone_number, decision["message"])
            self._add_to_conversation(phone_number, "assistant", decision["message"])
            session["step"] += 1
            return True
        else:
            self._complete_intervention(phone_number, decision)
            return True
    
    # ===== MODUS 2: BARRIER IDENTIFICATION =====
    
    def _handle_barrier_identification(self, phone_number: str, text: str, session: Dict) -> bool:
        """Modus 2: Hindernisse identifizieren und Strategien entwickeln - MAX 3 STEPS"""
        
        conversation = self._format_conversation(session["conversation"])
        step = session["step"]
        
        prompt = f"""Du bist ELLA in Barrier Identification (Problemlösetraining + Coping).

THERAPEUTISCHE TECHNIK: Problem-Solving Therapy (D'Zurilla & Nezu)
- Hindernisse antizipieren
- Konkrete Coping-Strategien entwickeln
- Mentale Vorbereitung auf Schwierigkeiten

ZIEL: User identifiziert Hindernisse und entwickelt Strategien

STEP: {step} von 3

DIALOG:
{conversation}

USER: "{text}"

FLOW:
1. Frage nach Hindernis → "Was könnte schwierig werden?" MIT Beispielen
2. Frage nach Strategie → "Was tust du wenn [Hindernis]?" MIT Beispielen
3. Abschluss → complete!

FRAGEN MIT BEISPIELEN:

Step 1 → 2:
"Verstehe! ✅ Was könnte dabei schwierig werden? Zum Beispiel:
• Andere könnten genervt reagieren
• Du könntest emotional werden
• Diskussion könnte eskalieren
• Zeitdruck könnte dich ablenken"

Step 2 → 3:
"Guter Punkt! ✅ Was machst du wenn das passiert? Zum Beispiel:
• Tief durchatmen bevor du antwortest
• Ruhig nachfragen: 'Wie meinst du das?'
• Kurze Pause machen
• Dir vorher überlegen was du sagen willst"

WICHTIG:
- BIAS zu "complete" ab Step 2
- Konkrete Strategien erfragen
- IMMER Validierung + konkrete Frage mit Beispielen
- Problemlöseorientiert: "Was ist deine Lösung?"
- NIEMALS "Schule"

ENTSCHEIDUNG:
- Step 2+: Starke Tendenz zu complete
- Step 3: IMMER complete

JSON:
{{
    "action": "continue|complete",
    "message": "VALIDIERUNG + KONKRETE FRAGE mit Beispielen (wenn continue)",
    "barriers": ["Liste von Hindernissen"],
    "strategies": ["Liste von Strategien"],
    "points": 1-2
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=350, temperature=0.8)
        decision = self._parse_json(response, {"action": "complete", "points": 1})
        
        # Update Data
        if decision.get("barriers"):
            session["data"]["barriers"].extend(decision["barriers"])
        if decision.get("strategies"):
            session["data"]["strategies"].extend(decision["strategies"])
        
        # Safety Check: Ab Step 2 → complete bias
        if step >= 2:
            decision["action"] = "complete"
        
        # Quality Check
        if decision["action"] == "continue":
            message = decision.get("message", "")
            if not message or "?" not in message:
                logger.warning("AI response missing question mark, forcing complete")
                decision["action"] = "complete"
        
        if decision["action"] == "continue":
            self.bot.send_message(phone_number, decision["message"])
            self._add_to_conversation(phone_number, "assistant", decision["message"])
            session["step"] += 1
            return True
        else:
            self._complete_intervention(phone_number, decision)
            return True
    
    # ===== MODUS 3: SKILL PRACTICE (ROLLENSPIEL) =====
    
    def _handle_skill_practice(self, phone_number: str, text: str, session: Dict) -> bool:
        """Modus 3: Dialog-Übung / Rollenspiel / Exposition in sensu - MAX 3 STEPS"""
        
        step = session["step"]
        
        # Step 1: Generiere Dialog-Szenario
        if step == 1:
            scenario = self._generate_dialog_scenario()
            session["data"]["dialog_practice"] = scenario
            
            message = (
                f"Lass uns das üben! 💪\n\n"
                f"Stell dir diese Situation vor:\n\n"
                f"{scenario}\n\n"
                f"Wie würdest du reagieren? Was würdest du sagen?"
            )
            
            self.bot.send_message(phone_number, message)
            self._add_to_conversation(phone_number, "assistant", message)
            session["step"] += 1
            return True
        
        # Step 2-3: User übt Antwort
        elif step in [2, 3]:
            conversation = self._format_conversation(session["conversation"])
            
            prompt = f"""Du bist ELLA in Skill Practice (Rollenspiel + Behavioral Rehearsal).

THERAPEUTISCHE TECHNIK: Behavioral Rehearsal (Verhaltenstherapie)
- Mentale Durchführung schwieriger Situationen
- Verhaltensrepertoire erweitern durch Übung
- Exposition in sensu (imaginativ)

STEP: {step} von 3

DIALOG:
{conversation}

USER ANTWORT: "{text}"

AUFGABE:
1. Gib kurzes Feedback (1-2 Sätze) mit Validierung
2. Würdige offene Haltung

Bei Step 2:
- Wenn Antwort gut → Stell Follow-up-Frage: "Und wenn die Person noch kritischer wird?"
- ODER complete wenn sehr gut

Bei Step 3:
- IMMER complete

WICHTIG:
- Würdige Übungsbereitschaft
- Fokus auf offene, neugierige Reaktionen
- IMMER Validierung + evtl. Frage
- Max 3 Sätze

JSON:
{{
    "action": "continue|complete",
    "message": "VALIDIERUNG + evtl. Follow-up-Frage",
    "points": 2-3
}}
"""
            
            response = self.ai._make_request(prompt, max_tokens=250, temperature=0.8)
            decision = self._parse_json(response, {"action": "complete", "points": 2})
            
            # Force complete bei Step 3
            if step >= 3:
                decision["action"] = "complete"
            
            # Quality Check nur für Step 2
            if step == 2 and decision["action"] == "continue":
                message = decision.get("message", "")
                if not message or "?" not in message:
                    logger.warning("AI response missing question mark, forcing complete")
                    decision["action"] = "complete"
            
            if decision["action"] == "continue":
                self.bot.send_message(phone_number, decision["message"])
                self._add_to_conversation(phone_number, "assistant", decision["message"])
                session["step"] += 1
                return True
            else:
                self._complete_intervention(phone_number, decision)
                return True
        
        else:
            # Sollte nicht passieren
            self._force_complete(phone_number, session)
            return True
    
    def _generate_dialog_scenario(self) -> str:
        """Generiert Dialog-Szenario für Skill Practice"""
        
        prompt = """Generiere kurzes Dialog-Szenario für Jugendliche (11-25).

ANFORDERUNGEN:
- 3-4 Zeilen Dialog zwischen 2 Personen
- Eine Person sagt etwas Kontroverses/Provokantes
- Andere Person soll offen reagieren
- Themen: Social Media, Klima, Politik, Alltag, etc.
- Namen verwenden
- NIEMALS "Schule" - stattdessen: "beim Lernen", "in Gruppen"

ZIEL: User übt offene, neugierige Reaktion

Beispiel:
"Lisa: 'TikTok ist totaler Müll. Pure Zeitverschwendung!'
Tom: 'Hm, ich weiß nicht...'
Lisa: 'Was gibt's da nicht zu wissen? Das ist Fakt!'
Du bist Tom. Wie reagierst du?"

Generiere ähnlich, anderes Thema."""
        
        scenario = self.ai._make_request(prompt, max_tokens=200, temperature=0.9)
        
        if not scenario or len(scenario) < 50:
            # Fallback
            scenarios = [
                """Alex: "Klimaproteste sind doch lächerlich. Bringt eh nichts!"
Jana: "Ich weiß nicht genau..."
Alex: "Was gibt's da nicht zu wissen?"
Du bist Jana. Wie reagierst du?""",
                
                """Max: "Leute die anders wählen als ich sind einfach dumm."
Sam: "Hmm..."
Max: "Ist doch so oder nicht?"
Du bist Sam. Wie reagierst du?""",
                
                """Kim: "Ich versteh nicht wie man vegan sein kann. Total unrealistisch!"
Chris: "Naja..."
Kim: "Komm, sag nicht dass du das gut findest?"
Du bist Chris. Wie reagierst du?"""
            ]
            import random
            return random.choice(scenarios)
        
        return scenario
    
    # ===== FALLBACK: GENERIC =====
    
    def _handle_generic(self, phone_number: str, text: str, session: Dict) -> bool:
        """Fallback wenn Modus unklar"""
        conversation = self._format_conversation(session["conversation"])
        
        prompt = f"""Führe Preparation-Intervention durch.

DIALOG:
{conversation}

USER: "{text}"

Step {session['step']} von 3.

Ab Step 2 → complete!

WICHTIG: Validierung + Frage (wenn continue)

JSON: {{"action": "continue|complete", "message": "VALIDIERUNG + FRAGE", "points": 1-2}}"""
        
        response = self.ai._make_request(prompt, max_tokens=200)
        decision = self._parse_json(response, {"action": "complete", "points": 1})
        
        if session["step"] >= 2:
            decision["action"] = "complete"
        
        if decision["action"] == "continue":
            self.bot.send_message(phone_number, decision["message"])
            self._add_to_conversation(phone_number, "assistant", decision["message"])
            session["step"] += 1
            return True
        else:
            self._complete_intervention(phone_number, decision)
            return True
    
    def _continue_conversation(self, phone_number: str, session: Dict) -> bool:
        """Helper für Fortsetzung der Konversation"""
        mode = session["mode"]
        
        if mode == "action_planning":
            return self._handle_action_planning(phone_number, "...", session)
        elif mode == "barrier_identification":
            return self._handle_barrier_identification(phone_number, "...", session)
        elif mode == "skill_practice":
            return self._handle_skill_practice(phone_number, "...", session)
        else:
            return self._handle_generic(phone_number, "...", session)
    
    # ===== COMPLETION =====
    
    def _complete_intervention(self, phone_number: str, decision: Dict):
        """Schließt Intervention ab"""
        session = self.sessions[phone_number]
        mode = session["mode"]
        
        points = decision.get("points", 1)
        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(points, self.bot)
        
        # Modus-spezifischer Abschluss
        closing = self._generate_closing(session, mode)
        self.bot.send_message(phone_number, closing)
        
        self._save_session_data(phone_number, session, points)
        if self.study_manager:

            pass  # advance_day disabled - day advances by real time only

        

        del self.sessions[phone_number]
        
        logger.info(f"Preparation completed: mode={mode}, steps={session['step']}, points={points}")
    
    def _force_complete(self, phone_number: str, session: Dict):
        """Erzwungen bei Step-Limit"""
        mode = session["mode"]
        logger.warning(f"Force completing preparation: mode={mode}, step={session['step']}")
        
        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(1, self.bot)
        
        closings = {
            "skill_practice": "Super geübt! Probier's in echt aus! 💪",
            "action_planning": "Super Plan! Du schaffst das! 💪",
            "barrier_identification": "Gut vorbereitet! Du bist bereit! 💪"
        }
        
        closing = closings.get(mode, "Super! Du bist bereit! 💪")
        self.bot.send_message(phone_number, closing)
        
        self._save_session_data(phone_number, session, points=1)
        if self.study_manager:

            pass  # advance_day disabled - day advances by real time only

        

        del self.sessions[phone_number]
    
    def _generate_closing(self, session: Dict, mode: str) -> str:
        """Generiert Abschluss"""
        conversation = self._format_conversation(session["conversation"])
        
        mode_info = {
            "skill_practice": {
                "technique": "Rollenspiel / Behavioral Rehearsal",
                "focus": "Dialog-Übung"
            },
            "action_planning": {
                "technique": "Implementation Intentions",
                "focus": "Konkreter Handlungsplan"
            },
            "barrier_identification": {
                "technique": "Problem-Solving Therapy",
                "focus": "Hindernisse & Strategien"
            }
        }
        
        info = mode_info.get(mode, {"technique": "Preparation", "focus": "Vorbereitung"})
        
        prompt = f"""Kurzer Abschluss für {info['focus']}.

THERAPEUTISCHE TECHNIK: {info['technique']}

DIALOG:
{conversation}

MAX 3 Sätze:
1. Würdige was User gemacht hat
2. Motiviere zur Umsetzung in der Realität
3. Emoji: 💪

WICHTIG:
- Keine Frage am Ende (Abschluss!)
- Fokus auf reale Umsetzung
- Selbstwirksamkeit stärken

Beispiel für skill_practice:
"Super geübt! Du hast verschiedene Reaktionen ausprobiert. Probier's beim nächsten Mal in echt aus! 💪"

Beispiel für action_planning:
"Dein Plan ist konkret! Beim nächsten [Situation]: [konkreter Plan]. Du schaffst das! 💪"

Beispiel für barrier_identification:
"Gut vorbereitet! Du weißt jetzt was schwierig werden kann und wie du damit umgehst. Du bist bereit! 💪"
"""
        
        response = self.ai._make_request(prompt, max_tokens=150, temperature=0.8)
        return response or "Super! Du bist bereit! 💪"
    
    def _emergency_complete(self, phone_number: str):
        """Notfall-Abschluss"""
        self.bot.send_message(phone_number, "Super! Du bist bereit! 💪")
        
        if phone_number in self.sessions:
            session = self.sessions[phone_number]
            self._save_session_data(phone_number, session, points=1, error=True)
            if self.study_manager:

                pass  # advance_day disabled - day advances by real time only

            

            del self.sessions[phone_number]
    
    # ===== HELPERS =====
    
    def _add_to_conversation(self, phone_number: str, role: str, content: str):
        self.sessions[phone_number]["conversation"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def _format_conversation(self, conversation: list) -> str:
        formatted = []
        for msg in conversation[-8:]:
            role = "ELLA" if msg["role"] == "assistant" else "User"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)
    
    def _parse_json(self, response: str, fallback: Dict) -> Dict:
        try:
            if "{" in response and "}" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                return json.loads(response[start:end])
        except:
            pass
        return fallback
    
    def _save_session_data(self, phone_number: str, session: Dict, points: int, error: bool = False):
        try:
            with open("../data/preparation_ai_sessions.jsonl", "a", encoding="utf-8") as f:
                data = {
                    "timestamp": datetime.now().isoformat(),
                    "phone_number": phone_number,
                    "mode": session["mode"],
                    "steps_completed": session["step"],
                    "max_steps": session["max_steps"],
                    "points_awarded": points,
                    "conversation": session["conversation"],
                    "data": session.get("data", {}),
                    "user_state": session["user_state_snapshot"],
                    "error": error,
                    "forced_complete": session["step"] >= session["max_steps"],
                    "version": "v2.0_max3_techniques"
                }
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Error saving: {e}")
    
    def is_active(self, phone_number: str) -> bool:
        return phone_number in self.sessions
    
    def get_active_users(self) -> list:
        return list(self.sessions.keys())
