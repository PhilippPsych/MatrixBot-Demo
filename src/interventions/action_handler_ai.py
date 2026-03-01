#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Powered Action Handler - IMPROVED
Handeln in der Realität - Drei Modi mit therapeutischen Techniken

IMPROVEMENTS:
- Konkretere Fragen mit Beispielen
- "Weiß nicht" Handling mit Wahlmöglichkeiten
- Alle Modi auf max 3 Steps reduziert
"""

import logging
import json
from typing import Dict, Optional
from datetime import datetime
from ai_service import AIService
from user_state_points import UserState

logger = logging.getLogger(__name__)


class AIActionHandler:
    """
    AI-gesteuerter Action Handler - IMPROVED
    
    Drei Modi mit therapeutischen Techniken:
    1. conflict_scenario: Konfliktsituationen üben (Experiential Learning)
    2. real_world_application: Reale Erfahrungen berichten (Exposition in vivo, Selbstmonitoring)
    3. success_sharing: Erfolge teilen (Verhaltensaktivierung, Selbstbeobachtung)
    
    ALLE MODI: MAX 3 STEPS
    """
    
    def __init__(self, bot_instance, study_manager=None):
        self.bot = bot_instance
        self.study_manager = study_manager
        self.ai = AIService()
        self.sessions: Dict[str, Dict] = {}
    
    def start_intervention(self, phone_number: str) -> bool:
        """AI wählt Modus und startet Action-Intervention"""
        if phone_number in self.sessions:
            logger.warning(f"Action already active for {phone_number}")
            return False
        
        user_state = UserState.load(phone_number)
        
        # AI wählt besten Modus
        intervention = self._ai_select_mode(user_state)
        mode = intervention["mode"]
        
        # Initialisiere Session mit STRIKTEN Limits
        self.sessions[phone_number] = {
            "mode": mode,  # conflict_scenario, real_world_application, success_sharing
            "start_time": datetime.now().isoformat(),
            "conversation": [],
            "step": 1,
            "max_steps": 3,  # ALLE MODI: 3 STEPS
            "data": {
                "situation": None,
                "actions_taken": [],
                "reflections": [],
                "learnings": []
            },
            "user_state_snapshot": {
                "level": user_state.level,
                "points": user_state.engagement_points,
                "total_interventions": user_state.total_interventions
            }
        }
        
        # Sende Opening
        opening = intervention["opening_message"]
        self.bot.send_message(phone_number, opening)
        self._add_to_conversation(phone_number, "assistant", opening)
        
        logger.info(f"Action started: mode={mode}, max_steps=3")
        
        return True
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Verarbeitet Antwort basierend auf Modus"""
        if phone_number not in self.sessions:
            return False
        
        session = self.sessions[phone_number]
        mode = session["mode"]
        self._add_to_conversation(phone_number, "user", text)
        
        # KRITISCH: Step-Limit Check ZUERST
        if session["step"] >= session["max_steps"]:
            logger.info(f"Action: Force complete at step {session['step']} (mode: {mode})")
            self._force_complete(phone_number, session)
            return True
        
        # Prüfe auf "weiß nicht" / unsichere Antworten
        if self._is_uncertain_response(text):
            return self._handle_uncertain_response(phone_number, text, session)
        
        try:
            # Modus-spezifische Verarbeitung
            if mode == "conflict_scenario":
                return self._handle_conflict_scenario(phone_number, text, session)
            elif mode == "real_world_application":
                return self._handle_real_world_application(phone_number, text, session)
            elif mode == "success_sharing":
                return self._handle_success_sharing(phone_number, text, session)
            else:
                # Fallback
                return self._handle_generic(phone_number, text, session)
                
        except Exception as e:
            logger.error(f"Error in Action ({mode}): {e}")
            self._emergency_complete(phone_number)
            return False
    
    def _is_uncertain_response(self, text: str) -> bool:
        """Erkennt unsichere/unklare Antworten"""
        uncertain_patterns = [
            "weiß nicht",
            "keine ahnung",
            "bin mir unsicher",
            "nicht sicher",
            "fällt mir nichts ein",
            "kann mich nicht erinnern",
            "hm",
            "hmm",
            "öhm",
            "ähm",
            "k.a.",
            "ka",
            "keine idee",
            "??"
        ]
        text_lower = text.lower().strip()
        return any(pattern in text_lower for pattern in uncertain_patterns) or len(text_lower) < 5
    
    def _handle_uncertain_response(self, phone_number: str, text: str, session: Dict) -> bool:
        """Bietet Wahlmöglichkeiten bei unsicheren Antworten"""
        mode = session["mode"]
        step = session["step"]
        
        # Modus-spezifische Beispiele
        examples = self._get_examples_for_mode(mode, step)
        
        prompt = f"""Du bist ELLA. User sagte: "{text}" (wirkt unsicher).

MODUS: {mode}
STEP: {step} von 3

Biete 2-3 KONKRETE Wahlmöglichkeiten als Inspiration.

{examples}

FORMAT:
"Kein Problem! Hier ein paar Ideen als Inspiration:

• [Beispiel 1]
• [Beispiel 2]
• [Beispiel 3]

Erkennst du dich in einem wieder? Oder war's was ganz anderes?"

WICHTIG:
- Konkrete, altersgerechte Beispiele (11-25 Jahre)
- Flexibler Kontext (Schule/Uni/Ausbildung/Alltag)
- Nicht wertend
- Max 4 Sätze
"""
        
        response = self.ai._make_request(prompt, max_tokens=250, temperature=0.8)
        
        if response:
            self.bot.send_message(phone_number, response)
            self._add_to_conversation(phone_number, "assistant", response)
            # Step NICHT erhöhen - gebe User noch eine Chance
            return True
        else:
            # Fallback
            return self._continue_conversation(phone_number, session)
    
    def _get_examples_for_mode(self, mode: str, step: int) -> str:
        """Gibt Beispiele für Modi und Steps zurück"""
        
        if mode == "conflict_scenario":
            if step == 1:
                return """BEISPIELE für hypothetische Konflikte:
• Gruppenprojekt wo einer nicht mitzieht
• Diskussion mit Eltern über Ausgehzeit
• Kollege kritisiert deine Arbeit
• Freunde haben andere Meinung zu Thema X"""
            elif step == 2:
                return """BEISPIELE für Handlungen:
• Ruhig nachfragen was los ist
• Eigene Meinung klar aber respektvoll sagen
• Kompromiss vorschlagen
• Um konkrete Beispiele bitten"""
        
        elif mode == "real_world_application":
            if step == 1:
                return """BEISPIELE für reale Situationen:
• Im Unterricht/Meeting verschiedene Meinungen gehört
• Mit Freunden über kontroverse Themen geredet
• Feedback von Lehrer/Chef bekommen das anders war als gedacht
• Jemand hat anders reagiert als erwartet"""
            elif step == 2:
                return """BEISPIELE für was passierte:
• Habe zugehört und dann meine Sicht erklärt
• War erst defensiv, dann offen geworden
• Habe nachgefragt um besser zu verstehen
• Konnte gut verschiedene Perspektiven abwägen"""
        
        elif mode == "success_sharing":
            if step == 1:
                return """BEISPIELE für Erfolge:
• Hab mich auf neue Perspektive eingelassen
• Konnte in Diskussion cool bleiben
• Habe aktiv nachgefragt statt anzunehmen
• War offen für Kritik und konnte was lernen"""
        
        return ""
    
    def _ai_select_mode(self, user_state: UserState) -> Dict:
        """AI wählt besten Modus für User"""
        
        prompt = f"""Du bist ELLA. Wähle den besten Action-Modus für User Level {user_state.level}.

DREI MODI (ALLE MAX 3 STEPS):

1. **conflict_scenario** (Experiential Learning)
   - User beschreibt HYPOTHETISCHE Konfliktsituation
   - Überlegt wie er/sie handeln würde
   - Fokus: Mentale Vorbereitung, "Was wenn..."
   
2. **real_world_application** (Exposition in vivo, Selbstmonitoring)
   - User berichtet von ECHTER Situation
   - Erzählt was passiert ist
   - Fokus: Alltagserfahrungen sammeln, Selbstbeobachtung
   
3. **success_sharing** (Verhaltensaktivierung, Positive Verstärkung)
   - User teilt ERFOLG oder positive Erfahrung
   - Reflektiert was gut lief
   - Fokus: Erfolge bewusst machen, Motivation stärken

WÄHLE basierend auf:
- Level 1-2: eher conflict_scenario (mental vorbereiten)
- Level 3+: real_world_application (Fokus auf echte Erfahrungen)
- Nach 3+ Action-Interventionen: success_sharing (Erfolge würdigen)
- Zufallselement: Variiere Modi

ZIELGRUPPE: Junge Menschen (11-25 Jahre)
- Schüler, Studenten, Azubis
- Flexibler Kontext (Uni/Ausbildung/Alltag)

OPENING MESSAGE:
- Kurz (2-3 Sätze)
- KONKRET mit Beispiel
- Passend zum Modus
- Aktivierend

JSON:
{{
    "mode": "conflict_scenario|real_world_application|success_sharing",
    "opening_message": "Deine Eröffnung mit KONKRETEM Beispiel",
    "rationale": "Warum dieser Modus?"
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=300, temperature=0.8)
        result = self._parse_json(response, {
            "mode": "real_world_application",
            "opening_message": "Zeit für Action! 💪\n\nErzähl mal: Gab's diese Woche eine Situation wo du offen für andere Meinungen warst?\n\nZum Beispiel: in Diskussion, bei Gruppenprojekt, oder im Gespräch mit Freunden?",
            "rationale": "fallback"
        })
        
        logger.info(f"AI selected mode: {result['mode']} ({result.get('rationale', 'no rationale')})")
        return result
    
    # ===== MODUS 1: CONFLICT SCENARIO (Experiential Learning) =====
    
    def _handle_conflict_scenario(self, phone_number: str, text: str, session: Dict) -> bool:
        """Modus 1: Hypothetische Konfliktsituation durchspielen - MAX 3 STEPS"""
        
        conversation = self._format_conversation(session["conversation"])
        step = session["step"]
        
        prompt = f"""Du bist ELLA in Conflict Scenario (Experiential Learning).

ZIEL: User denkt hypothetische Konfliktsituation durch
- "Was wenn..." Szenarien
- Mentale Vorbereitung
- Handlungsoptionen explorieren

STEP: {step} von 3

DIALOG:
{conversation}

USER: "{text}"

FLOW:
1. User beschreibt Situation → KONKRETE Nachfrage zu Handlung mit BEISPIEL
2. User überlegt Handlung → Kurze Reflektion ("Was könnte passieren?")
3. Abschluss → complete!

FRAGEN MIT BEISPIELEN:

Step 1 → 2:
"Und wie würdest du reagieren? Zum Beispiel:
• Ruhig nachfragen was los ist
• Deine Meinung klar sagen
• Einen Kompromiss vorschlagen

Was würde am besten passen?"

Step 2 → 3:
"Was glaubst du: Was könnte im besten Fall passieren? Und im schlechtesten?"

WICHTIG:
- BIAS zu "complete" ab Step 2
- Kurze Fragen (max 3 Sätze)
- IMMER mit konkreten Beispielen
- Hypothetisch: "Stell dir vor...", "Was wenn..."

ENTSCHEIDUNG:
- Step 2+: Starke Tendenz zu complete
- Step 3: IMMER complete

JSON:
{{
    "action": "continue|complete",
    "message": "Deine Nachricht MIT Beispielen (wenn continue)",
    "extracted": {{
        "situation": "Beschriebene Situation",
        "action": "Geplante Handlung",
        "reflection": "Reflektion"
    }},
    "points": 1-2
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=300, temperature=0.8)
        decision = self._parse_json(response, {"action": "complete", "points": 1})
        
        # Update Data
        if decision.get("extracted"):
            ext = decision["extracted"]
            if ext.get("situation"):
                session["data"]["situation"] = ext["situation"]
            if ext.get("action"):
                session["data"]["actions_taken"].append(ext["action"])
            if ext.get("reflection"):
                session["data"]["reflections"].append(ext["reflection"])
        
        # Safety Check: Ab Step 2 → complete bias, Step 3 → force complete
        if step >= 2:
            decision["action"] = "complete"
        
        if decision["action"] == "continue":
            self.bot.send_message(phone_number, decision["message"])
            self._add_to_conversation(phone_number, "assistant", decision["message"])
            session["step"] += 1
            return True
        else:
            self._complete_intervention(phone_number, decision)
            return True
    
    # ===== MODUS 2: REAL WORLD APPLICATION (Exposition in vivo) =====
    
    def _handle_real_world_application(self, phone_number: str, text: str, session: Dict) -> bool:
        """Modus 2: Reale Alltagserfahrungen berichten - MAX 3 STEPS"""
        
        conversation = self._format_conversation(session["conversation"])
        step = session["step"]
        
        prompt = f"""Du bist ELLA in Real World Application (Exposition in vivo, Selbstmonitoring).

ZIEL: User berichtet von ECHTER Situation
- Selbstbeobachtung fördern
- Alltagserfahrungen reflektieren
- "Was ist wirklich passiert?"

STEP: {step} von 3

DIALOG:
{conversation}

USER: "{text}"

FLOW:
1. User berichtet Situation → KONKRETE Nachfrage zu Details mit BEISPIEL
2. User gibt Details → Kurzes Learning ("Was hast du gelernt?")
3. Abschluss → complete!

FRAGEN MIT BEISPIELEN:

Step 1 → 2:
"Wie hast du dich dabei gefühlt? Und wie hat die andere Person reagiert?

Zum Beispiel:
• War überraschend offen
• Hat erstmal abgeblockt
• Wollte mehr wissen"

Step 2 → 3:
"Cool! Was nimmst du daraus mit? Was war wichtig für dich?"

WICHTIG:
- BIAS zu "complete" ab Step 2
- Kurze Fragen (max 3 Sätze)
- IMMER mit konkreten Beispielen
- Fokus auf ECHTE Erfahrung

ENTSCHEIDUNG:
- Step 2+: Starke Tendenz zu complete
- Step 3: IMMER complete

JSON:
{{
    "action": "continue|complete",
    "message": "Deine Nachricht MIT Beispielen (wenn continue)",
    "extracted": {{
        "situation": "Was ist passiert?",
        "details": "Wie lief es?",
        "learning": "Was gelernt?"
    }},
    "points": 1-2
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=300, temperature=0.8)
        decision = self._parse_json(response, {"action": "complete", "points": 1})
        
        # Update Data
        if decision.get("extracted"):
            ext = decision["extracted"]
            if ext.get("situation"):
                session["data"]["situation"] = ext["situation"]
            if ext.get("details"):
                session["data"]["actions_taken"].append(ext["details"])
            if ext.get("learning"):
                session["data"]["learnings"].append(ext["learning"])
        
        # Safety Check: Ab Step 2 → complete bias, Step 3 → force complete
        if step >= 2:
            decision["action"] = "complete"
        
        if decision["action"] == "continue":
            self.bot.send_message(phone_number, decision["message"])
            self._add_to_conversation(phone_number, "assistant", decision["message"])
            session["step"] += 1
            return True
        else:
            self._complete_intervention(phone_number, decision)
            return True
    
    # ===== MODUS 3: SUCCESS SHARING (Verhaltensaktivierung) =====
    
    def _handle_success_sharing(self, phone_number: str, text: str, session: Dict) -> bool:
        """Modus 3: Erfolge teilen und würdigen - MAX 3 STEPS"""
        
        conversation = self._format_conversation(session["conversation"])
        step = session["step"]
        
        prompt = f"""Du bist ELLA in Success Sharing (Verhaltensaktivierung, Positive Verstärkung).

ZIEL: User teilt ERFOLG
- Erfolge bewusst machen
- Positive Verstärkung
- Motivation stärken

STEP: {step} von 3

DIALOG:
{conversation}

USER: "{text}"

FLOW:
1. User teilt Erfolg → KONKRETE Nachfrage zu Details mit BEISPIEL
2. User gibt Details → Explizite Würdigung + Abschluss
3. Complete!

FRAGEN MIT BEISPIELEN:

Step 1 → 2:
"Das ist stark! 💪 Erzähl mehr:

• Wie hast du dich dabei gefühlt?
• Was war der beste Moment?
• Hat dich was überrascht?"

Step 2 → 3:
"Super gemacht! Was hat dir dabei am meisten geholfen?"

WICHTIG:
- EXPLIZITE Würdigung: "Das war stark!", "Super!", "Respekt!"
- Fokus auf POSITIVES
- Step 2: Bereits complete bias
- Step 3: IMMER complete

ENTSCHEIDUNG:
- Step 2+: Starke Tendenz zu complete
- Step 3: IMMER complete

JSON:
{{
    "action": "continue|complete",
    "message": "Würdigung + Frage MIT Beispielen (wenn continue)",
    "extracted": {{
        "success": "Was war erfolgreich?",
        "details": "Wie lief es?",
        "impact": "Was hat's gebracht?"
    }},
    "points": 2-3
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=300, temperature=0.8)
        decision = self._parse_json(response, {"action": "complete", "points": 2})
        
        # Update Data
        if decision.get("extracted"):
            ext = decision["extracted"]
            if ext.get("success"):
                session["data"]["situation"] = ext["success"]
            if ext.get("details"):
                session["data"]["actions_taken"].append(ext["details"])
            if ext.get("impact"):
                session["data"]["reflections"].append(ext["impact"])
        
        # Safety Check: Ab Step 2 → complete bias, Step 3 → force complete
        if step >= 2:
            decision["action"] = "complete"
        
        if decision["action"] == "continue":
            self.bot.send_message(phone_number, decision["message"])
            self._add_to_conversation(phone_number, "assistant", decision["message"])
            session["step"] += 1
            return True
        else:
            self._complete_intervention(phone_number, decision)
            return True
    
    # ===== FALLBACK: GENERIC =====
    
    def _handle_generic(self, phone_number: str, text: str, session: Dict) -> bool:
        """Fallback wenn Modus unklar"""
        conversation = self._format_conversation(session["conversation"])
        
        prompt = f"""Führe Action-Intervention durch.

DIALOG:
{conversation}

USER: "{text}"

Step {session['step']} von 3.

Ab Step 2 → complete!

JSON: {{"action": "continue|complete", "message": "...", "points": 1-2}}"""
        
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
        
        if mode == "conflict_scenario":
            return self._handle_conflict_scenario(phone_number, "...", session)
        elif mode == "real_world_application":
            return self._handle_real_world_application(phone_number, "...", session)
        elif mode == "success_sharing":
            return self._handle_success_sharing(phone_number, "...", session)
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
        
        logger.info(f"Action completed: mode={mode}, steps={session['step']}, points={points}")
    
    def _force_complete(self, phone_number: str, session: Dict):
        """Erzwingt Abschluss bei Step-Limit"""
        mode = session["mode"]
        logger.warning(f"Force completing action: mode={mode}, step={session['step']}")
        
        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(1, self.bot)
        
        closings = {
            "conflict_scenario": "Gut durchdacht! Du bist vorbereitet! 💪",
            "real_world_application": "Danke fürs Teilen! Weiter so! 💪",
            "success_sharing": "Stark! Bleib am Ball! 💪"
        }
        
        closing = closings.get(mode, "Super! Weiter so! 💪")
        self.bot.send_message(phone_number, closing)
        
        self._save_session_data(phone_number, session, points=1)
        if self.study_manager:

            pass  # advance_day disabled - day advances by real time only

        

        del self.sessions[phone_number]
    
    def _generate_closing(self, session: Dict, mode: str) -> str:
        """Generiert modus-spezifischen Abschluss"""
        conversation = self._format_conversation(session["conversation"])
        
        mode_focus = {
            "conflict_scenario": "Mentale Vorbereitung auf Konflikt",
            "real_world_application": "Reale Alltagserfahrung und Selbstbeobachtung",
            "success_sharing": "Erfolg teilen und positive Verstärkung"
        }
        
        prompt = f"""Kurzer Abschluss für {mode_focus.get(mode, 'Action')}.

DIALOG:
{conversation}

MODUS-SPEZIFISCH:

conflict_scenario:
- Würdige mentale Vorbereitung
- "Du bist bereit für die nächste Situation!"

real_world_application:
- Würdige Selbstbeobachtung
- Würdige dass User in der Realität gehandelt hat
- "Super, dass du das im Alltag ausprobiert hast!"

success_sharing:
- EXPLIZITE Würdigung des Erfolgs
- Positive Verstärkung: "Das war stark!", "Respekt!"
- Motiviere weiterzumachen

MAX 3 Sätze, aktivierend, Emoji: 💪

Beispiel (real_world_application):
"Cool, dass du das in echt ausprobiert hast! Du hast genau beobachtet, was passiert ist. Mach weiter so! 💪"
"""
        
        response = self.ai._make_request(prompt, max_tokens=150, temperature=0.8)
        return response or "Super! Weiter so! 💪"
    
    def _emergency_complete(self, phone_number: str):
        """Notfall-Abschluss"""
        self.bot.send_message(phone_number, "Danke! Weiter so! 💪")
        
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
            with open("../data/action_ai_sessions.jsonl", "a", encoding="utf-8") as f:
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
                    "forced_complete": session["step"] >= session["max_steps"]
                }
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Error saving: {e}")
    
    def is_active(self, phone_number: str) -> bool:
        return phone_number in self.sessions
    
    def get_active_users(self) -> list:
        return list(self.sessions.keys())
