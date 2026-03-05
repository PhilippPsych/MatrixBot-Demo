#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generic AI-Powered Handler Template - FIXED VERSION
Verbesserte Fehlerbehandlung und Logging
"""

import logging
import json
from typing import Dict, Optional, List
from datetime import datetime
from ai_service import AIService
from user_state_points import UserState

logger = logging.getLogger(__name__)


class AIPhaseHandler:
    """
    Generischer AI-gesteuerter Handler für beliebige Interventions-Phasen
    
    FIXED: Bessere Fehlerbehandlung in start_intervention()
    """
    
    def __init__(
        self,
        bot_instance,
        phase_name: str,
        phase_description: str,
        intervention_types: List[str],
        phase_specific_instructions: str = ""
    ):
        self.bot = bot_instance
        self.ai = AIService()
        self.phase_name = phase_name
        self.phase_description = phase_description
        self.intervention_types = intervention_types
        self.phase_specific_instructions = phase_specific_instructions
        self.sessions: Dict[str, Dict] = {}
    
    def start_intervention(self, phone_number: str) -> bool:
        """Startet AI-gesteuerte Intervention für diese Phase - MIT FEHLERBEHANDLUNG"""
        if phone_number in self.sessions:
            logger.warning(f"{self.phase_name} intervention already active for {phone_number}")
            return False
        
        try:
            user_state = UserState.load(phone_number)
            
            # AI wählt und erstellt Intervention
            logger.info(f"Attempting to select intervention for {self.phase_name} phase")
            intervention = self._ai_select_intervention(user_state)
            
            if not intervention:
                logger.error(f"_ai_select_intervention returned None/empty for {self.phase_name}")
                return False
            
            if "opening_message" not in intervention:
                logger.error(f"_ai_select_intervention missing 'opening_message' field for {self.phase_name}")
                logger.error(f"Intervention dict: {intervention}")
                return False
            
            # Initialisiere Session
            self.sessions[phone_number] = {
                "type": intervention.get("type", "unknown"),
                "start_time": datetime.now().isoformat(),
                "conversation": [],
                "step": 1,
                "max_steps": intervention.get("suggested_steps", 3),
                "user_context": intervention.get("context", {}),
                "opening_snippet": intervention.get("opening_message", ""),
                "style_note": "",
                "user_state_snapshot": {
                    "level": user_state.level,
                    "points": user_state.engagement_points,
                    "group": user_state.group
                }
            }
            
            # Sende Opening
            self.bot.send_message(phone_number, intervention["opening_message"])
            self._add_to_conversation(phone_number, "assistant", intervention["opening_message"])
            
            logger.info(f"{self.phase_name} intervention successfully started for {phone_number}")
            return True
        
        except Exception as e:
            logger.error(f"ERROR starting {self.phase_name} intervention for {phone_number}: {e}", exc_info=True)
            return False
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Verarbeitet User-Antwort mit AI"""
        if phone_number not in self.sessions:
            return False
        
        session = self.sessions[phone_number]
        self._add_to_conversation(phone_number, "user", text)
        
        try:
            # AI entscheidet über nächsten Schritt
            ai_decision = self._ai_process_response(phone_number, text, session)
            
            if ai_decision["action"] == "continue":
                self.bot.send_message(phone_number, ai_decision["message"])
                self._add_to_conversation(phone_number, "assistant", ai_decision["message"])
                session["step"] += 1
                if ai_decision.get("style_note"):
                    session["style_note"] = ai_decision["style_note"]

            elif ai_decision["action"] == "complete":
                if ai_decision.get("style_note"):
                    session["style_note"] = ai_decision["style_note"]
                self._complete_intervention(phone_number, ai_decision)
                
            elif ai_decision["action"] == "need_help":
                # User braucht Unterstützung
                help_message = self._ai_generate_help(phone_number, session)
                self.bot.send_message(phone_number, help_message)
                self._add_to_conversation(phone_number, "assistant", help_message)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in {self.phase_name} handler: {e}", exc_info=True)
            self._emergency_complete(phone_number)
            return False
    
    def _ai_select_intervention(self, user_state: UserState) -> Dict:
        """AI wählt beste Intervention für User in dieser Phase - MIT FEHLERBEHANDLUNG"""
        
        try:
            # Formatiere Intervention-Typen für Prompt
            types_description = "\n".join([
                f"{i+1}. {t}: {self._get_type_description(t)}" 
                for i, t in enumerate(self.intervention_types)
            ])
            
            prompt = f"""Du bist ELLA, ein Coach für Jugnendliche zu helfen offen zu sein für andere Meinungen. Wähle die beste {self.phase_name}-Intervention.

PHASE: {self.phase_name}
PHASE-ZIEL: {self.phase_description}

{self.phase_specific_instructions}

USER-PROFIL:
- Gruppe: {user_state.group}
- Level: {user_state.level}
- Punkte: {user_state.engagement_points}
- Bisherige Interventionen: {user_state.total_interventions}

BISHERIGE INTERVENTIONS-HISTORY:
{user_state.get_history_summary()}
→ Wähle einen Typ, der noch NICHT oder selten verwendet wurde.

VERFÜGBARE INTERVENTIONS-TYPEN:
{types_description}

AUFGABE:
1. Wähle den besten Typ für diesen User
2. Formuliere eine einladende Eröffnung (1-2 Sätze)
3. Jugendgerecht (11-16 Jahre), konkret, nicht belehrend

ANTWORT-FORMAT (JSON):
{{
    "type": "einer der obigen Typen",
    "opening_message": "Deine Eröffnungsnachricht",
    "rationale": "Warum dieser Typ?",
    "suggested_steps": 2,
    "context": {{"key": "value für Intervention-spezifische Daten"}}
}}
"""
            
            logger.info(f"Making AI request for {self.phase_name} intervention selection")
            response = self.ai._make_request(prompt, max_tokens=350, temperature=0.6)
            
            if not response:
                logger.warning(f"AI request returned empty response for {self.phase_name}")
                return self._get_fallback_intervention()
            
            logger.info(f"AI response received: {response[:100]}...")
            parsed = self._parse_json(response, self._get_fallback_intervention())
            
            logger.info(f"Parsed intervention: type={parsed.get('type')}, has_opening={bool(parsed.get('opening_message'))}")
            return parsed
        
        except Exception as e:
            logger.error(f"Exception in _ai_select_intervention for {self.phase_name}: {e}", exc_info=True)
            return self._get_fallback_intervention()
    
    def _ai_process_response(self, phone_number: str, text: str, session: Dict) -> Dict:
        """AI analysiert Antwort und entscheidet über Fortsetzung"""
        
        try:
            conversation = self._format_conversation(session["conversation"])
            
            prompt = f"""Du bist ELLA in einer {self.phase_name}-Intervention.

PHASE: {self.phase_name}
ZIEL: {self.phase_description}
INTERVENTION-TYP: {session["type"]}
SCHRITT: {session["step"]} von {session["max_steps"]}

BISHERIGER DIALOG:
{conversation}

USER ANTWORT: "{text}"

ENTSCHEIDUNGSLOGIK:

1. FORTSETZEN (continue):
   - User antwortet oberflächlich → max 1 Vertiefende Frage
   - Mehr Reflexion/Planung möglich
   - Noch kein natürlicher Abschluss

2. ABSCHLIESSEN (complete):
   - Phase-Ziel erreicht ({self.phase_description})
   - User hat substantiell beigetragen
   - Natürlicher Gesprächsabschluss

3. HILFE (need_help):
   - User ist blockiert oder unsicher
   - Beispiel oder Unterstützung nötig

VARIANZ-HINWEIS:
{UserState.load(phone_number).get_history_summary()}
→ Formuliere Validierung und Fragen anders als in den obigen Einstiegen.
→ Variiere: Satzstruktur, Beispiele, Fragestil (offen/Auswahl/hypothetisch).

PASSUNG VOR STRUKTUR:
Wenn der User etwas Unerwartetes oder Persönliches teilt, gehe darauf ein –
auch wenn das vom geplanten Schritt abweicht. Authentizität schlägt Struktur.

WICHTIG:
- Baue auf User-Antwort auf
- Konkrete Fragen mit Beispielen
- 1-2 Sätze
- Jugendgerecht

ANTWORT (JSON):
{{
    "action": "continue|complete|need_help",
    "message": "Deine Nachricht (nur bei continue/need_help)",
    "points": 1-3,
    "completion_summary": "Kurze Zusammenfassung (nur bei complete)",
    "style_note": "Kurze Beschreibung deines Stils in dieser Intervention (z.B. 'humorvoll', 'direkt-fragend', 'empathisch-erzählend')",
    "reasoning": "Warum diese Entscheidung?"
}}
"""
            
            response = self.ai._make_request(prompt, max_tokens=300, temperature=0.6)
            return self._parse_json(response, {
                "action": "complete",
                "message": "",
                "points": 1,
                "reasoning": "fallback"
            })
        
        except Exception as e:
            logger.error(f"Exception in _ai_process_response: {e}", exc_info=True)
            return {
                "action": "complete",
                "message": "",
                "points": 1,
                "reasoning": "error fallback"
            }
    
    def _ai_generate_help(self, phone_number: str, session: Dict) -> str:
        """AI generiert Hilfestellung wenn User blockiert ist"""
        try:
            conversation = self._format_conversation(session["conversation"])
            
            prompt = f"""User braucht Hilfe in {self.phase_name}-Intervention.

SITUATION:
{conversation}

Gib ein konkretes Beispiel oder Unterstützung (1-2 Sätze, jugendgerecht).
"""
            
            response = self.ai._make_request(prompt, max_tokens=150, temperature=0.7)
            return response or "Versuch es mal mit einem kleinen Schritt. Was wäre das einfachste, das du tun könntest?"
        
        except Exception as e:
            logger.error(f"Exception in _ai_generate_help: {e}", exc_info=True)
            return "Versuch es mal mit einem kleinen Schritt. Was wäre das einfachste, das du tun könntest?"
    
    def _complete_intervention(self, phone_number: str, ai_decision: Dict):
        """Schließt Intervention ab"""
        try:
            session = self.sessions[phone_number]
            
            # Vergebe Punkte
            points = ai_decision.get("points", 1)
            user_state = UserState.load(phone_number)
            user_state.add_engagement_points(points, self.bot)

            # History-Eintrag
            user_state.add_intervention_to_history(
                day=user_state.last_evaluation_day,
                phase=self.phase_name,
                type=session["type"],
                topic=session.get("user_context", {}).get("topic", session["type"]),
                opening_snippet=session.get("opening_snippet", ""),
                style_note=session.get("style_note", "")
            )

            # AI-generierte Abschlussnachricht
            closing = self._ai_generate_closing(phone_number, session)
            self.bot.send_message(phone_number, closing)
            
            # Speichere Daten
            self._save_session_data(phone_number, session, points)
            
            # Cleanup
            del self.sessions[phone_number]
            
            logger.info(f"{self.phase_name} completed for {phone_number}: {points} points")
        
        except Exception as e:
            logger.error(f"Exception in _complete_intervention: {e}", exc_info=True)
            self._emergency_complete(phone_number)
    
    def _ai_generate_closing(self, phone_number: str, session: Dict) -> str:
        """AI generiert Abschluss"""
        try:
            conversation = self._format_conversation(session["conversation"])
            
            prompt = f"""Generiere kurzen, wertschätzenden Abschluss für {self.phase_name}-Intervention.

DIALOG:
{conversation}

ANFORDERUNGEN:
- 1-2 Sätze
- Würdige Beitrag des Users
- Motivierend
- Jugendgerecht
"""
            
            response = self.ai._make_request(prompt, max_tokens=150, temperature=0.6)
            return response or "Danke für deine Gedanken! 💭"
        
        except Exception as e:
            logger.error(f"Exception in _ai_generate_closing: {e}", exc_info=True)
            return "Danke für deine Gedanken! 💭"
    
    def _emergency_complete(self, phone_number: str):
        """Notfall-Abschluss"""
        try:
            self.bot.send_message(phone_number, "Danke für deine Teilnahme! 💭")
            
            if phone_number in self.sessions:
                session = self.sessions[phone_number]
                self._save_session_data(phone_number, session, points=1, error=True)
                del self.sessions[phone_number]
        
        except Exception as e:
            logger.error(f"Exception even in _emergency_complete: {e}", exc_info=True)
    
    # ===== HELPER METHODS =====
    
    def _get_type_description(self, intervention_type: str) -> str:
        """Gibt Beschreibung für Interventions-Typ"""
        descriptions = {
            # Contemplation
            "situation_reflection": "User reflektiert über eigene Erfahrung",
            "story_discussion": "User diskutiert vorgegebene Geschichte",
            "emotion_exploration": "User erkundet eigene Gefühle",
            "perspective_shift": "User überlegt andere Sichtweisen",
            
            # Preparation
            "action_planning": "User plant konkrete Schritte",
            "barrier_identification": "User identifiziert Hindernisse",
            "skill_practice": "User übt Kommunikations-Skills",
            
            # Action
            "conflict_scenario": "User löst Konfliktsituation",
            "real_world_application": "User berichtet von echter Situation",
            "success_sharing": "User teilt Erfolge",
            
            # Maintenance
            "reflection": "User reflektiert über Fortschritt",
            "helping_others": "User gibt Tipps an andere",
            "challenge_mastery": "User meistert schwierige Situation"
        }
        return descriptions.get(intervention_type, "Intervention zur Förderung von Offenheit")
    
    def _get_fallback_intervention(self) -> Dict:
        """Fallback wenn AI-Selection fehlschlägt - MIT GARANTIERTEM opening_message"""
        logger.warning(f"Using fallback intervention for {self.phase_name}")
        
        # Phase-spezifische Fallback-Messages
        fallback_messages = {
            "Precontemplation": "Manchmal beschäftigen uns Dinge... Gibt es etwas, worüber du nachdenkst?",
            "Contemplation": "Hast du schon mal darüber nachgedacht, wie andere Leute Dinge sehen? Erzähl mal!",
            "Preparation": "Überleg mal: Was könntest du heute tun, um offener für andere Meinungen zu sein?",
            "Action": "Erzähl mal von einer Situation, wo du versucht hast, eine andere Meinung zu verstehen!",
            "Maintenance": "Wie gehst du mittlerweile mit unterschiedlichen Meinungen um? Was hat sich verändert?"
        }
        
        return {
            "type": self.intervention_types[0] if self.intervention_types else "generic",
            "opening_message": fallback_messages.get(self.phase_name, f"Lass uns über {self.phase_description.lower()} sprechen!"),
            "suggested_steps": 2,
            "context": {},
            "rationale": "fallback - AI unavailable"
        }
    
    def _add_to_conversation(self, phone_number: str, role: str, content: str):
        """Fügt Message zu Conversation hinzu"""
        if phone_number in self.sessions:
            self.sessions[phone_number]["conversation"].append({
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
    
    def _format_conversation(self, conversation: list) -> str:
        """Formatiert für AI-Prompts"""
        formatted = []
        for msg in conversation:
            role = "ELLA" if msg["role"] == "assistant" else "User"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)
    
    def _parse_json(self, response: str, fallback: Dict) -> Dict:
        """Parse JSON mit Fallback"""
        try:
            if not response:
                logger.warning(f"Empty response in _parse_json for {self.phase_name}")
                return fallback
            
            if "{" in response and "}" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
                parsed = json.loads(json_str)
                
                # Validiere dass wichtige Felder vorhanden sind
                if "opening_message" not in parsed and fallback.get("opening_message"):
                    logger.warning(f"Parsed JSON missing opening_message, using fallback")
                    return fallback
                
                return parsed
        except Exception as e:
            logger.warning(f"JSON parse failed in {self.phase_name}: {e}")
        
        return fallback
    
    def _save_session_data(self, phone_number: str, session: Dict, points: int, error: bool = False):
        """Speichert Session-Daten"""
        try:
            filepath = f"../data/{self.phase_name.lower()}_ai_sessions.jsonl"
            
            with open(filepath, "a", encoding="utf-8") as f:
                data = {
                    "timestamp": datetime.now().isoformat(),
                    "phone_number": phone_number,
                    "phase": self.phase_name,
                    "intervention_type": session["type"],
                    "duration_seconds": (
                        datetime.now() - datetime.fromisoformat(session["start_time"])
                    ).total_seconds(),
                    "steps_completed": session["step"],
                    "max_steps": session["max_steps"],
                    "points_awarded": points,
                    "conversation": session["conversation"],
                    "user_state": session["user_state_snapshot"],
                    "context": session.get("user_context", {}),
                    "error": error
                }
                
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"Error saving {self.phase_name} data: {e}", exc_info=True)
    
    # ===== STATUS METHODS =====
    
    def is_active(self, phone_number: str) -> bool:
        return phone_number in self.sessions
    
    def get_active_users(self) -> list:
        return list(self.sessions.keys())
    
    def get_session_info(self, phone_number: str) -> Optional[Dict]:
        return self.sessions.get(phone_number)


# ===== KONKRETE HANDLER-IMPLEMENTIERUNGEN =====

class PreparationHandler(AIPhaseHandler):
    """Preparation-Phase Handler"""
    def __init__(self, bot_instance):
        super().__init__(
            bot_instance=bot_instance,
            phase_name="Preparation",
            phase_description="User plant konkrete Schritte für mehr Offenheit",
            intervention_types=[
                "action_planning",
                "barrier_identification", 
                "skill_practice",
                "dialog_simulation"
            ],
            phase_specific_instructions="""
FOKUS: Vom Nachdenken ins Handeln kommen
- Konkrete, machbare Pläne entwickeln
- Hindernisse antizipieren
- Skills praktisch üben
-Schließe das Gespräch ab, sobald der User ein Beispiel realer Anwendung gegeben hat – nicht erst nach ausführlicher Reflexion
- Nutze nicht das Wort "Schule" oder "Studium" sondern nutze, wenn dann allgemeinere begriffe wie "Lernen"
"""
        )


class ActionHandler(AIPhaseHandler):
    """Action-Phase Handler"""
    def __init__(self, bot_instance):
        super().__init__(
            bot_instance=bot_instance,
            phase_name="Action",
            phase_description="User setzt Offenheit aktiv um und sammelt Erfahrungen",
            intervention_types=[
                "conflict_scenario",
                "real_world_reflection",
                "success_sharing",
                "challenge_mastery"
            ],
            phase_specific_instructions="""
FOKUS: Aktive Umsetzung und Reflexion
- Reale Situationen bearbeiten
- Erfolge feiern
- Aus Schwierigkeiten lernen
- Selbstwirksamkeit stärken
-Schließe das Gespräch ab, sobald der User ein Beispiel realer Anwendung gegeben hat – nicht erst nach ausführlicher Reflexion
- Nutze nicht das Wort "Schule" oder "Studium" sondern nutze, wenn dann allgemeinere begriffe wie "Lernen"
"""
        )


class MaintenanceHandler(AIPhaseHandler):
    """Maintenance-Phase Handler"""
    def __init__(self, bot_instance):
        super().__init__(
            bot_instance=bot_instance,
            phase_name="Maintenance",
            phase_description="User erhält und festigt erreichte Offenheit",
            intervention_types=[
                "progress_reflection",
                "peer_support",
                "advanced_challenges",
                "role_model"
            ],
            phase_specific_instructions="""
FOKUS: Verhalten stabilisieren und vertiefen
- Fortschritte würdigen
- Anderen helfen
- Neue Herausforderungen meistern
- Als Vorbild wirken
-Schließe das Gespräch ab, sobald der User ein Beispiel realer Anwendung gegeben hat – nicht erst nach ausführlicher Reflexion
- Nutze nicht das Wort "Schule" oder "Studium" sondern nutze, wenn dann allgemeinere begriffe wie "Lernen"
"""
        )
