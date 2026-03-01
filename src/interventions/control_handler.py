#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Control Condition Handler - Neutrale Mini-Interaktionen ohne ELLA-Elemente
"""

import logging
import random
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ControlHandler:
    """
    Kontrollbedingung: Neutrale Interaktionen ohne Validierung/Empathie/Skills
    Rotiert durch 5 Bausteine (Mo-Fr): Wissen, Valenz, Planung, Quiz, Beobachtung
    """
    
    def __init__(self, bot_instance, study_manager=None):
        self.bot = bot_instance
        self.study_manager = study_manager
        self.states: Dict[str, Dict] = {}
        
        # 5 Bausteine für Mo-Fr Rotation
        self.modules = [
            "wissen",      # Mo
            "valenz",      # Di
            "planung",     # Mi
            "quiz",        # Do
            "beobachtung"  # Fr
        ]
    
    def start_intervention(self, phone_number: str) -> bool:
        """Startet tägliche Control-Intervention basierend auf Wochentag"""
        if phone_number in self.states:
            logger.warning(f"Control intervention already active for {phone_number}")
            return False
        
        # Wochentag bestimmen (0=Mo, 1=Di, ..., 4=Fr)
        weekday = datetime.now().weekday()
        
        # Modulauswahl basierend auf Wochentag (cycling)
        module = self.modules[weekday % 5]
        
        self.states[phone_number] = {
            "module": module,
            "step": 1
        }
        
        # Modul starten
        if module == "wissen":
            return self._start_wissen(phone_number)
        elif module == "valenz":
            return self._start_valenz(phone_number)
        elif module == "planung":
            return self._start_planung(phone_number)
        elif module == "quiz":
            return self._start_quiz(phone_number)
        elif module == "beobachtung":
            return self._start_beobachtung(phone_number)
        
        return False
    
    # ===== MODUL 1: WISSEN =====
    
    def _start_wissen(self, phone_number: str) -> bool:
        """Wissens-Snack: Neutraler Fakt ohne Nachfrage"""
        facts = [
            "Die längste Bahnstrecke Europas ist die Transsibirische Eisenbahn (9.288 km).",
            "Der tiefste Punkt der Erde liegt im Marianengraben (etwa 11.000 m unter dem Meeresspiegel).",
            "Ein Tag auf der Venus ist länger als ein Jahr auf der Venus.",
            "Die Große Mauer ist etwa 21.196 km lang.",
            "Der Amazonas-Regenwald produziert etwa 20% des weltweiten Sauerstoffs.",
            "Island hat keine Wälder, aber über 200 Vulkane.",
            "Ein Blitz ist etwa 30.000°C heiß - fünfmal heißer als die Sonnenoberfläche.",
            "Die Sahara war vor 6.000 Jahren eine grüne Landschaft mit Seen.",
            "Honig verdirbt praktisch nie - man hat in ägyptischen Gräbern 3.000 Jahre alten Honig gefunden.",
            "Der Mount Everest wächst jedes Jahr etwa 4 mm."
        ]
        
        fact = random.choice(facts)
        
        self.bot.send_message(
            phone_number,
            f"Wusstest du?\n\n{fact}\n\n👍 / 👎"
        )
        return True
    
    # ===== MODUL 2: VALENZ =====
    
    def _start_valenz(self, phone_number: str) -> bool:
        """Valenz-Check: Kurze Stimmungsabfrage ohne Follow-up"""
        self.bot.send_message(
            phone_number,
            "Wie war dein Tag bisher?\n\n🙂 | 😐 | 🙁"
        )
        return True
    
    # ===== MODUL 3: PLANUNG =====
    
    def _start_planung(self, phone_number: str) -> bool:
        """Planungs-Ping: Einfache To-Do-Nennung ohne Zielarbeit"""
        self.bot.send_message(
            phone_number,
            "Nenne eine Sache, die du heute erledigen willst."
        )
        return True
    
    # ===== MODUL 4: QUIZ =====
    
    def _start_quiz(self, phone_number: str) -> bool:
        """Fakten-Quiz: Einfache Multiple-Choice-Frage"""
        quizzes = [
            {
                "question": "Wie viele Kontinente zählt man üblicherweise?",
                "options": ["5", "6", "7"],
                "correct": "7",
                "explanation": "Korrekt ist 7 (Europa, Asien, Afrika, Nordamerika, Südamerika, Australien, Antarktika)."
            },
            {
                "question": "Welches ist der größte Planet in unserem Sonnensystem?",
                "options": ["Saturn", "Jupiter", "Neptun"],
                "correct": "Jupiter",
                "explanation": "Korrekt ist Jupiter."
            },
            {
                "question": "Wie viele Zähne hat ein erwachsener Mensch normalerweise?",
                "options": ["28", "32", "36"],
                "correct": "32",
                "explanation": "Korrekt ist 32 (inkl. Weisheitszähne)."
            },
            {
                "question": "Welches Tier kann nicht rückwärts laufen?",
                "options": ["Elefant", "Känguru", "Pferd"],
                "correct": "Känguru",
                "explanation": "Korrekt ist Känguru."
            },
            {
                "question": "In welchem Jahr fiel die Berliner Mauer?",
                "options": ["1987", "1989", "1991"],
                "correct": "1989",
                "explanation": "Korrekt ist 1989."
            }
        ]
        
        quiz = random.choice(quizzes)
        self.states[phone_number]["quiz"] = quiz
        
        options_str = " / ".join(quiz["options"])
        
        self.bot.send_message(
            phone_number,
            f"{quiz['question']}\n\n{options_str}"
        )
        return True
    
    # ===== MODUL 5: BEOBACHTUNG =====
    
    def _start_beobachtung(self, phone_number: str) -> bool:
        """Achtsame Beobachtung: Einfache Wahrnehmungsübung ohne Reflexion"""
        self.bot.send_message(
            phone_number,
            "Schau dich 10 Sekunden um und nenne 1 Ding, das du siehst."
        )
        return True
    
    # ===== MESSAGE HANDLING =====
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Verarbeitet Antworten auf Control-Interventionen"""
        if phone_number not in self.states:
            return False
        
        state = self.states[phone_number]
        module = state["module"]
        
        try:
            if module == "wissen":
                return self._handle_wissen(phone_number, text, state)
            elif module == "valenz":
                return self._handle_valenz(phone_number, text, state)
            elif module == "planung":
                return self._handle_planung(phone_number, text, state)
            elif module == "quiz":
                return self._handle_quiz(phone_number, text, state)
            elif module == "beobachtung":
                return self._handle_beobachtung(phone_number, text, state)
        
        except Exception as e:
            logger.error(f"Error in control module {module}: {e}")
            self.bot.send_message(phone_number, "Danke für deine Teilnahme.")
            self._award_points(phone_number, state)
            self._save_data(phone_number, state, error=True)
            self._cleanup_state(phone_number)
        
        return False
    
    def _handle_wissen(self, phone_number: str, text: str, state: Dict) -> bool:
        """Behandelt Antwort auf Wissens-Snack"""
        state["response"] = text
        
        # Keine Nachfrage, nur Bestätigung
        self.bot.send_message(phone_number, "Danke.")
        
        self._award_points(phone_number, state)
        self._save_data(phone_number, state)
        self._cleanup_state(phone_number)
        return True
    
    def _handle_valenz(self, phone_number: str, text: str, state: Dict) -> bool:
        """Behandelt Valenz-Check"""
        state["valence"] = text
        
        # Nur loggen, keine Rückfrage oder Tipps
        self.bot.send_message(phone_number, "Notiert.")
        
        self._award_points(phone_number, state)
        self._save_data(phone_number, state)
        self._cleanup_state(phone_number)
        return True
    
    def _handle_planung(self, phone_number: str, text: str, state: Dict) -> bool:
        """Behandelt Planungs-Ping"""
        state["plan"] = text
        
        # Keine Zielarbeit, kein Selbstwirksamkeits-Nudge
        self.bot.send_message(phone_number, "Danke, notiert.")
        
        self._award_points(phone_number, state)
        self._save_data(phone_number, state)
        self._cleanup_state(phone_number)
        return True
    
    def _handle_quiz(self, phone_number: str, text: str, state: Dict) -> bool:
        """Behandelt Quiz-Antwort"""
        quiz = state.get("quiz", {})
        state["answer"] = text
        
        # Direktes Auflösen, kein Lob/Coaching
        self.bot.send_message(phone_number, quiz.get("explanation", "Danke."))
        
        self._award_points(phone_number, state)
        self._save_data(phone_number, state)
        self._cleanup_state(phone_number)
        return True
    
    def _handle_beobachtung(self, phone_number: str, text: str, state: Dict) -> bool:
        """Behandelt Beobachtung"""
        state["observation"] = text
        
        # Nur Bestätigung, keine Emotions-/Körper-/Kognitionsreflexion
        self.bot.send_message(phone_number, "Danke.")
        
        self._award_points(phone_number, state)
        self._save_data(phone_number, state)
        self._cleanup_state(phone_number)
        return True
    
    # ===== UTILITIES =====
    
    def _award_points(self, phone_number: str, state: Dict):
        """Vergibt Punkte (gleich wie ELLA-Bedingung)"""
        from user_state_points import UserState
        
        user_state = UserState.load(phone_number)
        
        # Einfach: 1 Punkt pro Teilnahme
        points = 1
        
        user_state.add_engagement_points(points, self.bot)
    
    def _save_data(self, phone_number: str, state: Dict, error: bool = False):
        """Speichert Control-Daten"""
        try:
            with open("../data/control_data.txt", "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                module = state.get("module", "unknown")
                
                # Modul-spezifische Daten
                if module == "wissen":
                    data = state.get("response", "")
                elif module == "valenz":
                    data = state.get("valence", "")
                elif module == "planung":
                    data = state.get("plan", "")
                elif module == "quiz":
                    quiz = state.get("quiz", {})
                    data = f"{quiz.get('question', '')} | {state.get('answer', '')}"
                elif module == "beobachtung":
                    data = state.get("observation", "")
                else:
                    data = ""
                
                error_flag = "ERROR" if error else "OK"
                
                f.write(f"{timestamp} | {phone_number} | {module} | {data} | {error_flag}\n")
        
        except Exception as e:
            logger.error(f"Error saving control data: {e}")
    
    def _cleanup_state(self, phone_number: str):
        """Räumt Zustand auf"""
        if phone_number in self.states:
            del self.states[phone_number]
    
    def is_active(self, phone_number: str) -> bool:
        """Prüft ob Control-Intervention aktiv"""
        return phone_number in self.states
    
    def get_active_users(self) -> list:
        """Gibt aktive User zurück"""
        return list(self.states.keys())
