#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ella-Bot für Matrix - Mit 10-Tage Studienprotokoll + Kontrollbedingung + ID-Code
Migriert von Signal zu Matrix/Synapse
"""

import os
import json
import time
import datetime
import threading
import schedule
import logging  
import random
from typing import Dict, List, Optional, Set
from dotenv import load_dotenv

from matrix_adapter_sidecar import MatrixBot, MatrixMessage
from ai_service import AIService
from user_state_points import UserState

# Intervention Handler Imports
from interventions.precontemplation_handler_ai import AIPrecontemplationHandler
from interventions.contemplation_handler_ai import AIContemplationHandler
from interventions.preparation_handler_ai import AIPreparationHandler
from interventions.action_handler_ai import AIActionHandler
from interventions.maintenance_handler_ai import AIMaintenanceHandler
from interventions.control_handler import ControlHandler

# Configuration
load_dotenv()
MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER")
MATRIX_USER_ID = os.getenv("MATRIX_USER_ID")
MATRIX_ACCESS_TOKEN = os.getenv("MATRIX_ACCESS_TOKEN")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
PILOT_MODE = os.getenv("PILOT_MODE", "false").lower() == "true"

# Study Configuration
STUDY_DURATION_DAYS = 10
MORNING_INTERVENTION_TIME = "09:00"  # 9:00 AM
SURVEY_URL = "https://umfragenup.uni-potsdam.de/Recept/"

# Test Times - für mehrere Interventionen am Tag (nur wenn MULTI_TIME_TEST aktiviert)
MULTI_TIME_TEST = False  # Setze auf True zum Testen mehrerer Zeiten
TEST_TIMES = ["14:05", "14:10", "14:15"]  # Mehrere Testzeiten

# Dynamic paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')
USER_STATES_DIR = os.path.join(DATA_DIR, 'user_states')

# Logging Setup
os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'ella_bot.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Ensure directories
for directory in [DATA_DIR, LOGS_DIR, USER_STATES_DIR]:
    os.makedirs(directory, exist_ok=True)


class UserDataManager:
    """Manages user data persistence"""
    
    @staticmethod
    def save_user_data(phone_number: str, answer1: str, answer2: str, group: str, age: Optional[int] = None, condition: str = "intervention", id_code: str = ""):
        """Save user registration data"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_data_file = os.path.join(DATA_DIR, 'user_data.txt')
        with open(user_data_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} | {phone_number} | {age or ''} | {answer1} | {answer2} | {group} | {condition} | {id_code}\n")
    
    @staticmethod
    def get_user_group(phone_number: str) -> Optional[str]:
        """Get user's assigned group"""
        user_data_file = os.path.join(DATA_DIR, 'user_data.txt')
        try:
            with open(user_data_file, "r", encoding="utf-8") as f:
                for line in reversed(f.readlines()):
                    parts = line.strip().split(" | ")
                    if len(parts) >= 6 and parts[1].strip() == phone_number:
                        return parts[5].strip()
        except FileNotFoundError:
            pass
        return None
    
    @staticmethod
    def get_user_condition(phone_number: str) -> str:
        """Get user's assigned condition (intervention/control)"""
        user_data_file = os.path.join(DATA_DIR, 'user_data.txt')
        try:
            with open(user_data_file, "r", encoding="utf-8") as f:
                for line in reversed(f.readlines()):
                    parts = line.strip().split(" | ")
                    if len(parts) >= 7 and parts[1].strip() == phone_number:
                        return parts[6].strip()
                    elif len(parts) >= 6 and parts[1].strip() == phone_number:
                        # Alte Einträge ohne condition → default intervention
                        return "intervention"
        except FileNotFoundError:
            pass
        return "intervention"  # Default


class SubscriptionManager:
    """Manages user subscriptions"""
    
    def __init__(self):
        self.subscribers: Set[str] = set()
        self._load_subscribers()
    
    def add_subscriber(self, phone_number: str):
        """Add subscriber"""
        if phone_number not in self.subscribers:
            self.subscribers.add(phone_number)
            subscribers_file = os.path.join(DATA_DIR, 'subscribers.txt')
            with open(subscribers_file, "a") as f:
                f.write(phone_number + "\n")
    
    def remove_subscriber(self, phone_number: str):
        """Remove subscriber"""
        self.subscribers.discard(phone_number)
        subscribers_file = os.path.join(DATA_DIR, 'subscribers.txt')
        try:
            with open(subscribers_file, "r") as f:
                lines = f.readlines()
            with open(subscribers_file, "w") as f:
                for line in lines:
                    if line.strip() != phone_number:
                        f.write(line)
        except FileNotFoundError:
            pass
    
    def _load_subscribers(self):
        """Load subscribers from file"""
        subscribers_file = os.path.join(DATA_DIR, 'subscribers.txt')
        try:
            with open(subscribers_file, "r") as f:
                self.subscribers = set(line.strip() for line in f.readlines())
        except FileNotFoundError:
            self.subscribers = set()


class StudyManager:
    """Manages 10-day study protocol"""
    
    def __init__(self, bot: MatrixBot):
        self.bot = bot
        self.completed_users: Set[str] = set()
        self._load_completed_users()
    
    def is_study_active(self, phone_number: str) -> bool:
        """Check if user's study period is still active"""
        if phone_number in self.completed_users:
            return False
        
        user_state = UserState.load(phone_number)
        
        if not user_state.start_date:
            return False
        
        try:
            start_date = datetime.datetime.fromisoformat(user_state.start_date)
            days_elapsed = (datetime.datetime.now() - start_date).days
            return days_elapsed < STUDY_DURATION_DAYS
        except:
            return False
    
    def get_study_day(self, phone_number: str) -> int:
        """Get current study day (1-10)"""
        user_state = UserState.load(phone_number)
        
        if not user_state.start_date:
            return 0
        
        try:
            start_date = datetime.datetime.fromisoformat(user_state.start_date)
            days_elapsed = (datetime.datetime.now() - start_date).days
            return min(days_elapsed + 1, STUDY_DURATION_DAYS)
        except:
            return 0
    
    def advance_day_for_test(self, phone_number: str):
        """TEST_MODE: Springe zum nächsten Tag nach abgeschlossener Intervention"""
        if not TEST_MODE and not PILOT_MODE:
            return
        
        user_state = UserState.load(phone_number)
        if not user_state.start_date:
            return
        
        try:
            # Setze start_date 1 Tag zurück = simuliert "nächster Tag"
            start_date = datetime.datetime.fromisoformat(user_state.start_date)
            new_start_date = start_date - datetime.timedelta(days=1)
            user_state.start_date = new_start_date.isoformat()
            user_state.save()
            
            new_day = self.get_study_day(phone_number)
            logger.info(f"🧪 TEST_MODE: Advanced {phone_number} to Day {new_day}/10")
        except Exception as e:
            logger.error(f"Error advancing test day: {e}")
    
    def check_and_complete_study(self, phone_number: str, reassessment_manager=None) -> bool:
        """Check if study should be completed and start re-assessment"""
        if phone_number in self.completed_users:
            return False
        
        user_state = UserState.load(phone_number)
        
        if not user_state.start_date:
            return False
        
        try:
            start_date = datetime.datetime.fromisoformat(user_state.start_date)
            days_elapsed = (datetime.datetime.now() - start_date).days
            
            if days_elapsed >= STUDY_DURATION_DAYS - 1:  # days_elapsed is 0-indexed, so day 10 = 9
                # Start re-assessment instead of sending completion directly
                if reassessment_manager:
                    reassessment_manager.start_reassessment(phone_number, user_state)
                    logger.info(f"Started re-assessment for {phone_number} (Day {days_elapsed + 1})")
                else:
                    # Fallback: alte Methode
                    self._send_completion_message(phone_number)
                    self._mark_completed(phone_number)
                return True
            
        except Exception as e:
            logger.error(f"Error checking study completion for {phone_number}: {e}")
        
        return False
    
    def _send_completion_message(self, phone_number: str):
        """Send study completion message with survey link"""
        user_state = UserState.load(phone_number)
        
        completion_message = (
            f"Die 10-Tage-Studie ist abgeschlossen!\n\n"
            f"Vielen Dank für deine Teilnahme und dein Engagement!\n\n"
            f"Dein Abschluss-Status:\n"
            f"• Level: {user_state.level}\n"
            f"• Punkte: {user_state.engagement_points}\n"
            f"• Übungen: {user_state.total_interventions}\n\n"
            f"Bitte fülle jetzt noch diese kurze Abschlussbefragung aus:\n"
            f"{SURVEY_URL}\n\n"
            f"Deine Antworten helfen uns, die Studie auszuwerten und politische Bildung zu verbessern.\n\n"
            f"Nochmals herzlichen Dank für deine Unterstützung!\n"
            f"Das Ella-Team"
        )
        
        self.bot.send_message(phone_number, completion_message)
        logger.info(f"Study completed for {phone_number}")
    
    def _mark_completed(self, phone_number: str):
        """Mark user as study completed"""
        self.completed_users.add(phone_number)
        
        completed_file = os.path.join(DATA_DIR, 'study_completed.txt')
        with open(completed_file, "a") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{timestamp} | {phone_number}\n")
    
    def _load_completed_users(self):
        """Load list of users who completed the study"""
        completed_file = os.path.join(DATA_DIR, 'study_completed.txt')
        try:
            with open(completed_file, "r") as f:
                for line in f:
                    parts = line.strip().split(" | ")
                    if len(parts) >= 2:
                        self.completed_users.add(parts[1].strip())
        except FileNotFoundError:
            pass
    
    def has_intervention_today(self, phone_number: str) -> bool:
        """Check if user already had intervention today"""
        user_state = UserState.load(phone_number)
        
        if not user_state.last_intervention_date:
            return False
        
        try:
            last_date = datetime.datetime.fromisoformat(user_state.last_intervention_date)
            today = datetime.datetime.now().date()
            return last_date.date() == today
        except:
            return False


class InterventionManager:
    """Manages all intervention handlers"""
    
    def __init__(self, bot: MatrixBot, study_manager):
        self.bot = bot
        self.study_manager = study_manager
        self.handlers = {
            "Precontemplation": AIPrecontemplationHandler(bot, study_manager),
            "Contemplation": AIContemplationHandler(bot, study_manager),
            "Preparation": AIPreparationHandler(bot, study_manager),
            "Action": AIActionHandler(bot, study_manager),
            "Maintenance": AIMaintenanceHandler(bot, study_manager)
        }
        # Control handler (nicht stage-abhängig)
        self.control_handler = ControlHandler(bot, study_manager)
    
    def start_for_user(self, phone_number: str, group: str, condition: str = "intervention") -> bool:
        """Start appropriate intervention based on condition"""
        
        # Control-Bedingung: Nutze ControlHandler
        if condition == "control":
            if not self.control_handler.is_active(phone_number):
                success = self.control_handler.start_intervention(phone_number)
                
                if success:
                    # Update last intervention date
                    user_state = UserState.load(phone_number)
                    user_state.last_intervention_date = datetime.datetime.now().isoformat()
                    user_state.save()
                
                return success
            return False
        
        # Interventions-Bedingung: Nutze stage-basierte Handler
        if group in self.handlers:
            handler = self.handlers[group]
            if not handler.is_active(phone_number):
                try:
                    success = handler.start_intervention(phone_number)
                    
                    if success:
                        # Update last intervention date
                        user_state = UserState.load(phone_number)
                        user_state.last_intervention_date = datetime.datetime.now().isoformat()
                        user_state.save()
                    
                    return success
                except Exception as e:
                    logger.error(f"Exception starting intervention for {phone_number}: {e}")
                    return False
        return False
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Handle message through active interventions"""
        # Check control handler first
        if self.control_handler.is_active(phone_number):
            return self.control_handler.handle_message(phone_number, text)
        
        # Check stage handlers
        for handler in self.handlers.values():
            if handler.is_active(phone_number):
                return handler.handle_message(phone_number, text)
        return False
    
    def cleanup_user(self, phone_number: str):
        """Clean up intervention states"""
        # Cleanup control
        if self.control_handler.is_active(phone_number):
            self.control_handler._cleanup_state(phone_number)
        
        # Cleanup stage handlers
        for handler in self.handlers.values():
            if handler.is_active(phone_number):
                handler._cleanup_state(phone_number)


class ReEvaluationManager:
    """Point-based re-evaluation system"""
    
    def __init__(self, bot: MatrixBot):
        self.bot = bot
        self.pending_reevaluations: Dict[str, Dict] = {}
    
    def is_due(self, phone_number: str) -> bool:
        """Check if re-evaluation is due (every 10 points)"""
        user_state = UserState.load(phone_number)
        return user_state.needs_reevaluation()
    
    def start_reevaluation(self, phone_number: str) -> bool:
        """Start re-evaluation"""
        if phone_number in self.pending_reevaluations:
            return False
        
        user_state = UserState.load(phone_number)
        user_state.pending_reevaluation = True
        user_state.save()
        
        evaluation_round = user_state.reevaluation_count + 1
        
        self.pending_reevaluations[phone_number] = {
            "step": "intro",
            "round": evaluation_round,
            "responses": []
        }
        
        self.bot.send_message(
            phone_number,
            f"Zeit für deine {evaluation_round}. Re-Evaluation!\n\n"
            f"Du hast {user_state.engagement_points} Punkte erreicht. "
            f"Zeit zu schauen, wo du stehst.\n\n"
            f"Bereit? Dann antworte mit 'ja' um zu beginnen."
        )
        
        return True
    
    def handle_message(self, phone_number: str, message: str) -> bool:
        """Handle re-evaluation messages"""
        if phone_number not in self.pending_reevaluations:
            return False
        
        state = self.pending_reevaluations[phone_number]
        
        try:
            if state["step"] == "intro":
                if message.lower().strip() in ['ja', 'yes', 'ok', 'bereit']:
                    return self._send_question_1(phone_number)
                else:
                    self.bot.send_message(phone_number, "Antworte mit 'ja' wenn du bereit bist.")
                    return True
            
            elif state["step"] == "question_1":
                if message.lower() in ['a', 'b', 'c', 'd', 'e']:
                    state["responses"].append({"question": "openness", "answer": message.lower()})
                    return self._send_question_2(phone_number)
                else:
                    self.bot.send_message(phone_number, "Bitte antworte mit: a, b, c, d oder e")
                    return True
            
            elif state["step"] == "question_2":
                if message.lower() in ['a', 'b']:
                    state["responses"].append({"question": "frequency", "answer": message.lower()})
                    return self._finalize_reevaluation(phone_number)
                else:
                    self.bot.send_message(phone_number, "Bitte antworte mit: a oder b")
                    return True
        
        except Exception as e:
            logger.error(f"Error in reevaluation: {e}")
        
        return False
    
    def _send_question_1(self, phone_number: str) -> bool:
        """Send first re-evaluation question"""
        self.pending_reevaluations[phone_number]["step"] = "question_1"
        
        self.bot.send_message(
            phone_number,
            "Wie offen bist du dafür, dich mit Meinungen zu beschäftigen, die ganz anders sind als deine?\n\n"
            "a) Ich bin nicht offen dafür und will das auch nicht ändern.\n\n"
            "b) Ich bin wenig offen dafür, könnte mir aber vorstellen, in den nächsten 6 Monaten offener zu werden.\n\n"
            "c) Ich bin etwas offen dafür und habe mir vorgenommen, in den nächsten 30 Tagen offener zu werden.\n\n"
            "d) Ich bin ziemlich offen dafür und bin bereits in den letzten 6 Monaten offener geworden.\n\n"
            "e) Ich bin sehr offen dafür und bin bereits seit mehr als 6 Monaten offener geworden.\n\n"
            "Bitte antworte mit: a, b, c, d oder e"
        )
        return True
    
    def _send_question_2(self, phone_number: str) -> bool:
        """Send second re-evaluation question"""
        self.pending_reevaluations[phone_number]["step"] = "question_2"
        
        self.bot.send_message(
            phone_number,
            "Frage 2: Hast du dich in den letzten 7 Tagen bewusst mit Meinungen beschäftigt, die ganz anders sind als deine?\n\n"
            "a) ja\nb) nein\n\n"
            "Bitte antworte mit: a oder b"
        )
        return True
    
    def _finalize_reevaluation(self, phone_number: str) -> bool:
        """Finalize re-evaluation"""
        try:
            state = self.pending_reevaluations[phone_number]
            responses = state["responses"]
            
            # Determine new group
            answer1 = next(r["answer"] for r in responses if r["question"] == "openness")
            answer2 = next(r["answer"] for r in responses if r["question"] == "frequency")
            
            if answer1 == 'a':
                new_group = "Precontemplation"
            elif answer1 == 'b':
                new_group = "Contemplation"
            elif answer1 == 'c' and answer2 == 'a':
                new_group = "Contemplation"
            elif answer1 == 'c' and answer2 != 'a':
                new_group = "Preparation"
            elif answer1 == 'd':
                new_group = "Action"
            elif answer1 == 'e':
                new_group = "Maintenance"
            else:
                new_group = "Unknown"
            
            current_group = UserDataManager.get_user_group(phone_number)
            
            # Save re-evaluation data
            self._save_reevaluation_data(phone_number, state["round"], responses, new_group, current_group)
            
            # Update user state
            user_state = UserState.load(phone_number)
            user_state.mark_reevaluation_done()
            
            # Update group if changed
            if new_group != current_group and new_group != "Unknown":
                current_condition = UserDataManager.get_user_condition(phone_number)
                UserDataManager.save_user_data(phone_number, answer1, answer2, new_group, condition=current_condition)
                self.bot.send_message(
                    phone_number,
                    f"Danke für deine Antworten!\n\n"
                    f"Deine Entwicklung: {current_group} → {new_group}\n\n"
                    f"Du wechselst zur {new_group}-Phase und erhältst ab sofort passende neue Übungen."
                )
            else:
                self.bot.send_message(
                    phone_number,
                    f"Danke für deine Antworten!\n\n"
                    f"Du bleibst in der {current_group}-Phase.\n\n"
                    f"Du machst gute Fortschritte - weiter so!"
                )
            
            # Cleanup
            del self.pending_reevaluations[phone_number]
            return True
        
        except Exception as e:
            logger.error(f"Error finalizing reevaluation: {e}")
            return False
    
    def _save_reevaluation_data(self, phone_number: str, round_num: int, responses: List[Dict], 
                               new_group: str, old_group: str):
        """Save re-evaluation results"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        reevaluation_file = os.path.join(DATA_DIR, 'reevaluation_data.txt')
        with open(reevaluation_file, "a", encoding="utf-8") as f:
            answer1 = next(r["answer"] for r in responses if r["question"] == "openness")
            answer2 = next(r["answer"] for r in responses if r["question"] == "frequency")
            
            f.write(f"{timestamp} | {phone_number} | Round_{round_num} | {answer1} | {answer2} | {old_group} | {new_group}\n")


class OnboardingManager:
    """Handles user onboarding"""
    
    def __init__(self, bot: MatrixBot):
        self.bot = bot
        self.onboarding_users: Dict[str, Dict] = {}
    
    def start_onboarding(self, phone_number: str):
        """Start onboarding"""
        self.onboarding_users[phone_number] = {"step": "awaiting_age"}
        self.bot.send_message(
            phone_number,
            "Lass uns starten! Wie alt bist Du?\n\n(Bitte gib dein Alter als Zahl ein, z.B. 25)"
        )
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Handle onboarding messages"""
        if phone_number not in self.onboarding_users:
            return False
        
        state = self.onboarding_users[phone_number]
        
        if state["step"] == "awaiting_age":
            return self._handle_age_input(phone_number, text)
        elif state["step"] == "awaiting_q1":
            return self._handle_question_1(phone_number, text)
        elif state["step"] == "awaiting_q2":
            return self._handle_question_2(phone_number, text)
        elif state["step"] == "awaiting_id_code":
            return self._handle_id_code(phone_number, text)
        
        return False
    
    def _handle_age_input(self, phone_number: str, text: str) -> bool:
        """Handle age input"""
        try:
            age = int(text.strip())
            if not 10 <= age <= 99:
                raise ValueError()
        except:
            self.bot.send_message(phone_number, "Bitte gib dein Alter als Zahl ein (z.B. 25).")
            return True
        
        self.onboarding_users[phone_number]["age"] = age
        self.onboarding_users[phone_number]["step"] = "awaiting_q1"
        
        self.bot.send_message(
            phone_number,
            f"Danke! Du bist {age} Jahre alt.\n\n"
            "Jetzt folgen 2 kurze Fragen, um die für dich passenden Reflexionsübungen zu finden:\n\n"
            "Wie offen bist du dafür, dich mit Meinungen zu beschäftigen, die ganz anders sind als deine?\n\n"
            "a) Ich bin nicht offen dafür und will das auch nicht ändern.\n\n"
            "b) Ich bin wenig offen dafür, könnte mir aber vorstellen, in den nächsten 6 Monaten offener zu werden.\n\n"
            "c) Ich bin etwas offen dafür und habe mir vorgenommen, in den nächsten 30 Tagen offener zu werden.\n\n"
            "d) Ich bin ziemlich offen dafür und bin bereits in den letzten 6 Monaten offener geworden.\n\n"
            "e) Ich bin sehr offen dafür und bin bereits seit mehr als 6 Monaten offener geworden.\n\n"
            "Bitte antworte mit: a, b, c, d oder e"
        )
        return True
    
    def _handle_question_1(self, phone_number: str, text: str) -> bool:
        """Handle first question"""
        if text.lower() not in ['a', 'b', 'c', 'd', 'e']:
            self.bot.send_message(phone_number, "Bitte antworte mit: a, b, c, d oder e")
            return True
        
        self.onboarding_users[phone_number]["answer1"] = text.lower()
        self.onboarding_users[phone_number]["step"] = "awaiting_q2"
        
        self.bot.send_message(
            phone_number,
            "Frage 2: Hast du dich in den letzten 7 Tagen bewusst mit Meinungen beschäftigt, die ganz anders sind als deine?\n\n"
            "a) ja\nb) nein\n\n"
            "Bitte antworte mit: a oder b"
        )
        return True
    
    def _handle_question_2(self, phone_number: str, text: str) -> bool:
        """Handle second question"""
        if text.lower() not in ['a', 'b']:
            self.bot.send_message(phone_number, "Bitte antworte mit: a oder b")
            return True
        
        self.onboarding_users[phone_number]["answer2"] = text.lower()
        self.onboarding_users[phone_number]["step"] = "awaiting_id_code"
        
        # Send ID code instructions
        self.bot.send_message(
            phone_number,
            "Perfekt! Jetzt noch eine letzte Sache:\n\n"
            "📋 Bildung eines ID-Codes\n\n"
            "Um deine Daten einander zuordnen zu können, erstellst du einen anonymen Versuchspersonen-Code. "
            "So können wir mehrere Fragebögen miteinander verknüpfen, ohne deinen tatsächlichen Namen zu kennen.\n\n"
            "Zur Bildung des Codes gehst du folgendermaßen vor:\n\n"
            "1️⃣ Erster Buchstabe des Vornamens der Mutter (z.B. Heike = H)\n"
            "2️⃣ Letzter Buchstabe des Geburtsortes (z.B. Berlin = N)\n"
            "3️⃣ Tag des Geburtstags als zweistellige Zahl (z.B. '08')\n"
            "4️⃣ Zweite Ziffer der Postleitzahl des Geburtsortes (z.B. 12345 = 2)\n"
            "5️⃣ Anzahl der Buchstaben des Geburtsmonats (z.B. '5' für April)\n\n"
            "Im Beispiel wäre der Code: HN0825\n\n"
            "Bitte trage deinen Code hier ein:"
        )
        return True
    
    def _handle_id_code(self, phone_number: str, text: str) -> bool:
        """Handle ID code input and complete onboarding"""
        id_code = text.strip().upper()
        
        # Basic validation: should be 5-6 characters
        if len(id_code) < 5 or len(id_code) > 7:
            self.bot.send_message(
                phone_number, 
                "Dein Code sollte etwa 5-6 Zeichen haben. "
                "Bitte überprüfe deine Eingabe und versuche es nochmal."
            )
            return True
        
        state = self.onboarding_users[phone_number]
        answer1 = state["answer1"]
        answer2 = state["answer2"]
        
        # Determine group (für beide Bedingungen gleich)
        if answer1 == 'a':
            group = "Precontemplation"
        elif answer1 == 'b':
            group = "Contemplation"
        elif answer1 == 'c' and answer2 == 'a':
            group = "Contemplation"
        elif answer1 == 'c' and answer2 != 'a':
            group = "Preparation"
        elif answer1 == 'd':
            group = "Action"
        elif answer1 == 'e':
            group = "Maintenance"
        else:
            group = "Unknown"
        
        # RANDOMISIERUNG: 50/50 zu intervention oder control
        condition = random.choice(["intervention", "control"])
        
        # Save data mit condition und id_code
        UserDataManager.save_user_data(phone_number, answer1, answer2, group, state.get("age"), condition, id_code)
        
        # Initialize user state with study start
        user_state = UserState.load(phone_number)
        user_state.start_date = datetime.datetime.now().isoformat()
        user_state.group = group
        user_state.save()
        
        # Complete onboarding
        del self.onboarding_users[phone_number]
        
        # Bedingungsspezifische Nachricht
        self.bot.send_message(
            phone_number,
            f"Perfekt! Dein Code '{id_code}' wurde gespeichert.\n\n"
            f"Du wurdest der Gruppe '{group}' zugeordnet.\n\n"
            f"Wie es funktioniert:\n"
            f"• Jeden Morgen um {MORNING_INTERVENTION_TIME} Uhr erhältst du eine kurze Übung\n"
            f"• Jede Übung gibt Punkte\n"
            f"• Die Studie läuft 10 Tage\n\n"
            f"Die erste Übung kommt morgen früh.\n\n"
            f"Nutze help um alle Befehle zu sehen.",
            formatted_body=(
                f"Perfekt! Dein Code '{id_code}' wurde gespeichert.<br><br>"
                f"Du wurdest der Gruppe '{group}' zugeordnet.<br><br>"
                f"Wie es funktioniert:<br>"
                f"• Jeden Morgen um {MORNING_INTERVENTION_TIME} Uhr erhältst du eine kurze Übung<br>"
                f"• Jede Übung gibt Punkte<br>"
                f"• Die Studie läuft 10 Tage<br><br>"
                f"Die erste Übung kommt morgen früh.<br><br>"
                f"Nutze <strong>help</strong> um alle Befehle zu sehen."
            )
        )
        
        return True


class ReAssessmentManager:
    """Handles post-study re-assessment (same 2 questions as onboarding)"""
    
    def __init__(self, bot_instance, study_manager, pilot_mode: bool = False):
        self.bot = bot_instance
        self.study_manager = study_manager
        self.pilot_mode = pilot_mode
        self.reassessment_users: Dict[str, Dict] = {}
    
    def start_reassessment(self, phone_number: str, user_state):
        """Start re-assessment for user who completed 10 days"""
        self.reassessment_users[phone_number] = {
            "step": "awaiting_q1",
            "user_state": user_state
        }
        
        self.bot.send_message(
            phone_number,
            "🎉 Herzlichen Glückwunsch! Du hast die 10 Tage geschafft!\n\n"
            "Bevor wir abschließen, möchte ich dir noch einmal die gleichen 2 Fragen stellen wie am Anfang.\n\n"
            "Wie offen bist du dafür, dich mit Meinungen zu beschäftigen, die ganz anders sind als deine?\n\n"
            "a) Ich bin nicht offen dafür und will das auch nicht ändern.\n\n"
            "b) Ich bin wenig offen dafür, könnte mir aber vorstellen, in den nächsten 6 Monaten offener zu werden.\n\n"
            "c) Ich bin etwas offen dafür und habe mir vorgenommen, in den nächsten 30 Tagen offener zu werden.\n\n"
            "d) Ich bin ziemlich offen dafür und bin bereits in den letzten 6 Monaten offener geworden.\n\n"
            "e) Ich bin sehr offen dafür und bin bereits seit mehr als 6 Monaten offener geworden.\n\n"
            "Bitte antworte mit: a, b, c, d oder e"
        )
        
        logger.info(f"Started re-assessment for {phone_number}")
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Handle re-assessment messages"""
        if phone_number not in self.reassessment_users:
            return False
        
        state = self.reassessment_users[phone_number]
        
        if state["step"] == "awaiting_q1":
            return self._handle_question_1(phone_number, text)
        elif state["step"] == "awaiting_q2":
            return self._handle_question_2(phone_number, text)
        
        return False
    
    def _handle_question_1(self, phone_number: str, text: str) -> bool:
        """Handle first question"""
        if text.lower() not in ['a', 'b', 'c', 'd', 'e']:
            self.bot.send_message(phone_number, "Bitte antworte mit: a, b, c, d oder e")
            return True
        
        self.reassessment_users[phone_number]["post_q1"] = text.lower()
        self.reassessment_users[phone_number]["step"] = "awaiting_q2"
        
        self.bot.send_message(
            phone_number,
            "Frage 2: Hast du dich in den letzten 7 Tagen bewusst mit Meinungen beschäftigt, die ganz anders sind als deine?\n\n"
            "a) ja\nb) nein\n\n"
            "Bitte antworte mit: a oder b"
        )
        return True
    
    def _handle_question_2(self, phone_number: str, text: str) -> bool:
        """Handle second question and complete re-assessment"""
        if text.lower() not in ['a', 'b']:
            self.bot.send_message(phone_number, "Bitte antworte mit: a oder b")
            return True
        
        state = self.reassessment_users[phone_number]
        state["post_q2"] = text.lower()
        
        post_q1 = state["post_q1"]
        post_q2 = state["post_q2"]
        user_state = state["user_state"]
        
        # Save post-assessment data
        self._save_post_assessment(phone_number, post_q1, post_q2)
        
        # Clean up
        del self.reassessment_users[phone_number]
        
        # Mark study as completed
        self.study_manager._mark_completed(phone_number)
        
        # Send completion message
        if self.pilot_mode:
            # PILOT_MODE: Kein Survey-Link
            completion_message = (
                f"Vielen Dank für deine Antworten!\n\n"
                f"📊 Dein Abschluss-Status:\n"
                f"• Level: {user_state.level}\n"
                f"• Punkte: {user_state.engagement_points}\n"
                f"• Übungen: {user_state.total_interventions}\n\n"
                f"Die Studie ist damit abgeschlossen.\n\n"
                f"Vielen Dank für deine Teilnahme! 🙏\n"
                f"Das Ella-Team"
            )
        else:
            # PRODUCTION_MODE: Mit Survey-Link
            completion_message = (
                f"Vielen Dank für deine Antworten!\n\n"
                f"📊 Dein Abschluss-Status:\n"
                f"• Level: {user_state.level}\n"
                f"• Punkte: {user_state.engagement_points}\n"
                f"• Übungen: {user_state.total_interventions}\n\n"
                f"Bitte fülle jetzt noch diese kurze Abschlussbefragung aus:\n"
                f"{SURVEY_URL}\n\n"
                f"Deine Antworten helfen uns, die Studie auszuwerten und politische Bildung zu verbessern.\n\n"
                f"Nochmals herzlichen Dank für deine Unterstützung!\n"
                f"Das Ella-Team"
            )
        
        self.bot.send_message(phone_number, completion_message)
        logger.info(f"Re-assessment completed for {phone_number}: post_q1={post_q1}, post_q2={post_q2}")
        return True
    
    def _save_post_assessment(self, phone_number: str, post_q1: str, post_q2: str):
        """Save post-assessment answers"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reassessment_file = os.path.join(DATA_DIR, 'reassessment_data.txt')
        
        with open(reassessment_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} | {phone_number} | {post_q1} | {post_q2}\n")
        
        logger.info(f"Saved post-assessment data for {phone_number}")



class EllaChatBot:
    """Main bot class with 10-day study protocol"""
    
    def __init__(self):
        self.ai_service = AIService()
        
        # Managers
        self.bot = MatrixBot(MATRIX_HOMESERVER, MATRIX_USER_ID, MATRIX_ACCESS_TOKEN)
        self.subscription_manager = SubscriptionManager()
        self.study_manager = StudyManager(self.bot)
        self.intervention_manager = InterventionManager(self.bot, self.study_manager)
        self.reevaluation_manager = ReEvaluationManager(self.bot)
        self.onboarding_manager = OnboardingManager(self.bot)
        self.reassessment_manager = ReAssessmentManager(self.bot, self.study_manager, pilot_mode=PILOT_MODE)
        self._register_handlers()
        self._setup_scheduler()
    
    def _register_handlers(self):
        """Register message handlers"""
        self.bot.add_handler("command:start", self.handle_start)
        self.bot.add_handler("command:stop", self.handle_stop)
        self.bot.add_handler("command:help", self.handle_help)
        self.bot.add_handler("command:info", self.handle_info)
        self.bot.add_handler("command:progress", self.handle_progress)
        self.bot.add_handler("message", self.handle_message)
        
        # Debug commands
        if TEST_MODE or PILOT_MODE:
            self.bot.add_handler("command:debug", self.handle_debug)
            self.bot.add_handler("command:trigger_intervention", self.handle_trigger_intervention)
            self.bot.add_handler("command:mygroup", self.handle_mygroup)
            self.bot.add_handler("command:trigger_reevaluation", self.handle_trigger_reevaluation)
            self.bot.add_handler("command:Trigger_reevaluation", self.handle_trigger_reevaluation)
            self.bot.add_handler("command:advance_day", self.handle_advance_day)
            self.bot.add_handler("command:reset", self.handle_reset)
            #self.bot.add_handler("command:complete_study", self.handle_complete_study)
    
    def handle_start(self, message: MatrixMessage):
        """Handle /start"""
        phone_number = message.sender
        logger.info(f"Start command from {phone_number}")
        
        group = UserDataManager.get_user_group(phone_number)
        if group:
            # Check if study completed
            if phone_number in self.study_manager.completed_users:
                self.bot.send_message(
                    phone_number,
                    "Du hast die 10-Tage-Studie bereits abgeschlossen.\n\n"
                    f"Falls du die Umfrage noch nicht ausgefüllt hast:\n{SURVEY_URL}\n\n"
                    "Vielen Dank für deine Teilnahme!"
                )
                return
            
            self.subscription_manager.add_subscriber(phone_number)
            user_state = UserState.load(phone_number)
            study_day = self.study_manager.get_study_day(phone_number)
            
            self.bot.send_message(
                phone_number,
                f"Willkommen zurück bei Ella!\n\n"
                f"Studientag: {study_day}/10\n"
                f"Gruppe: {group}\n"
                f"Level: {user_state.level} | Punkte: {user_state.engagement_points}\n\n"
                f"Die nächste Übung kommt um {MORNING_INTERVENTION_TIME} Uhr.\n\n"
                f"Nutze progress für Details oder help für alle Befehle.",
                formatted_body=(
                    f"Willkommen zurück bei Ella!<br><br>"
                    f"Studientag: {study_day}/10<br>"
                    f"Gruppe: {group}<br>"
                    f"Level: {user_state.level} | Punkte: {user_state.engagement_points}<br><br>"
                    f"Die nächste Übung kommt um {MORNING_INTERVENTION_TIME} Uhr.<br><br>"
                    f"Nutze <strong>progress</strong> für Details oder <strong>help</strong> für alle Befehle."
                )
            )
        else:
            self.subscription_manager.add_subscriber(phone_number)
            self.bot.send_message(
                phone_number,
                "Hi! Ich bin Ella - dein Empathic Learning & Listening Assistant!\n\n"
                "Du nimmst an einer 10-tägigen Studie teil:\n"
                "• Jeden Morgen erhältst du eine Reflexionsübung\n"
                "• Du sammelst Punkte für deine Teilnahme\n"
                "• Nach 10 Tagen gibt es eine kurze Abschlussbefragung\n\n"
                "Bereit?"
            )
            time.sleep(2)
            self.onboarding_manager.start_onboarding(phone_number)
    
    def handle_stop(self, message: MatrixMessage):
        """Handle /stop"""
        phone_number = message.sender
        self.subscription_manager.remove_subscriber(phone_number)
        self.intervention_manager.cleanup_user(phone_number)
        
        user_state = UserState.load(phone_number)
        study_day = self.study_manager.get_study_day(phone_number)
        
        self.bot.send_message(
            phone_number,
            f"Auf Wiedersehen!\n\n"
            f"Dein Stand:\n"
            f"• Studientag: {study_day}/10\n"
            f"• Level: {user_state.level}\n"
            f"• Punkte: {user_state.engagement_points}\n"
            f"• Übungen: {user_state.total_interventions}\n\n"
            f"Du kannst dich jederzeit mit /start wieder anmelden.\n\n"
            f"Danke fürs Mitmachen!"
        )
    
    def handle_help(self, message: MatrixMessage):
        """Handle /help"""
        phone_number = message.sender
        help_text = """Ella-Bot Hilfe

Verfügbare Befehle:
• start - Registrierung und Einstieg
• stop - Bot beenden
• progress - Zeigt deinen Fortschritt
• help - Diese Hilfe
• info - Infos über Ella

10-Tage-Studie:
• Jeden Morgen um 9:00 Uhr gibt es eine Übung
• Sammle Punkte durch Teilnahme
• Nach 10 Tagen: Abschlussbefragung

Punktesystem:
• 1 Punkt pro Übung
• 2 Punkte für ausführliche Antworten
• Alle 10 Punkte: Re-Evaluation"""

        help_html = (
            "Ella-Bot Hilfe<br><br>"
            "Verfügbare Befehle:<br>"
            "• <strong>start</strong> - Registrierung und Einstieg<br>"
            "• <strong>stop</strong> - Bot beenden<br>"
            "• <strong>progress</strong> - Zeigt deinen Fortschritt<br>"
            "• <strong>help</strong> - Diese Hilfe<br>"
            "• <strong>info</strong> - Infos über Ella<br><br>"
            "10-Tage-Studie:<br>"
            "• Jeden Morgen um 9:00 Uhr gibt es eine Übung<br>"
            "• Sammle Punkte durch Teilnahme<br>"
            "• Nach 10 Tagen: Abschlussbefragung<br><br>"
            "Punktesystem:<br>"
            "• 1 Punkt pro Übung<br>"
            "• 2 Punkte für ausführliche Antworten<br>"
            "• Alle 10 Punkte: Re-Evaluation"
        )

        if TEST_MODE:
            help_text += "\n\nTEST-MODUS:\n• debug - System-Status\n• mygroup - Aktuelle Gruppe\n• trigger_intervention - Intervention starten\n• advance_day - Tag vorrücken\n• trigger_reevaluation - Re-Evaluation\n• reset - Account zurücksetzen"
            help_html += (
                "<br><br>TEST-MODUS:<br>"
                "• <strong>debug</strong> - System-Status<br>"
                "• <strong>mygroup</strong> - Aktuelle Gruppe<br>"
                "• <strong>trigger_intervention</strong> - Intervention starten<br>"
                "• <strong>advance_day</strong> - Tag vorrücken<br>"
                "• <strong>trigger_reevaluation</strong> - Re-Evaluation<br>"
                "• <strong>reset</strong> - Account zurücksetzen"
            )

        self.bot.send_message(phone_number, help_text, formatted_body=help_html)
    
    def handle_info(self, message: MatrixMessage):
        """Handle /info"""
        phone_number = message.sender
        self.bot.send_message(
            phone_number,
            "Über Ella-Bot\n\n"
            "Name: Ella (Empathic Learning & Listening Assistant)\n\n"
            "Studiendesign:\n"
            "• 10-Tage-Interventionsstudie\n"
            "• Tägliche Reflexionsübungen\n"
            "• Punktebasiertes Feedback-System\n\n"
            "Wissenschaftlicher Hintergrund:\n"
            "• Basiert auf dem Transtheoretischen Modell\n"
            "• Entwickelt für politische Bildung\n"
            "• Erforscht von der Universität Potsdam\n\n"
            "Die 5 Lernphasen:\n"
            "1. Precontemplation\n"
            "2. Contemplation\n"
            "3. Preparation\n"
            "4. Action\n"
            "5. Maintenance\n\n"
            "Kontakt: jakob.fink-lamotte@uni-potsdam.de"
        )
    
    def handle_progress(self, message: MatrixMessage):
        """Handle /progress"""
        phone_number = message.sender
        user_state = UserState.load(phone_number)
        group = UserDataManager.get_user_group(phone_number)
        
        if not group:
            self.bot.send_message(phone_number, "Du bist noch nicht registriert. Nutze /start um zu beginnen.")
            return
        
        study_day = self.study_manager.get_study_day(phone_number)
        days_remaining = max(0, STUDY_DURATION_DAYS - study_day)
        
        progress_message = (
            f"Dein Fortschritt:\n\n"
            f"Studientag: {study_day}/10 ({days_remaining} Tage verbleibend)\n"
            f"Gruppe: {group}\n"
            f"Level: {user_state.level}\n"
            f"Punkte: {user_state.engagement_points}\n"
            f"Übungen: {user_state.total_interventions}\n"
            f"Re-Evaluationen: {user_state.reevaluation_count}\n\n"
        )
        
        points_to_next = 10 - (user_state.engagement_points % 10)
        if points_to_next > 0:
            progress_message += f"Noch {points_to_next} Punkte bis zur nächsten Re-Evaluation"
        
        self.bot.send_message(phone_number, progress_message)
    
    def handle_debug(self, message: MatrixMessage):
        """Handle /debug"""
        if not TEST_MODE and not PILOT_MODE:
            return
        
        phone_number = message.sender
        user_state = UserState.load(phone_number)
        group = UserDataManager.get_user_group(phone_number)
        condition = UserDataManager.get_user_condition(phone_number)
        study_day = self.study_manager.get_study_day(phone_number)
        
        active_handlers = []
        for name, handler in self.intervention_manager.handlers.items():
            if handler.is_active(phone_number):
                active_handlers.append(name)
        
        if self.intervention_manager.control_handler.is_active(phone_number):
            active_handlers.append("Control")
        
        debug_info = f"""Debug-Info:

User: {phone_number[:15]}...
Studientag: {study_day}/10
Gruppe: {group or 'Nicht registriert'}
Bedingung: {condition}
Level: {user_state.level}
Punkte: {user_state.engagement_points}
Interventionen: {user_state.total_interventions}
Hatte heute Intervention: {'Ja' if self.study_manager.has_intervention_today(phone_number) else 'Nein'}
Studie aktiv: {'Ja' if self.study_manager.is_study_active(phone_number) else 'Nein'}
Studie abgeschlossen: {'Ja' if phone_number in self.study_manager.completed_users else 'Nein'}
Aktive Handler: {', '.join(active_handlers) if active_handlers else 'Keine'}
Test-Modus: Aktiv"""

        self.bot.send_message(phone_number, debug_info)
    
    def handle_mygroup(self, message: MatrixMessage):
        """Handle /mygroup"""
        if not TEST_MODE and not PILOT_MODE:
            return
        
        phone_number = message.sender
        group = UserDataManager.get_user_group(phone_number)
        
        if group:
            user_state = UserState.load(phone_number)
            study_day = self.study_manager.get_study_day(phone_number)
            self.bot.send_message(
                phone_number, 
                f"Studientag: {study_day}/10\n"
                f"Gruppe: {group}\n"
                f"Level: {user_state.level}\n"
                f"Punkte: {user_state.engagement_points}"
            )
        else:
            self.bot.send_message(phone_number, "Du bist noch nicht registriert. Nutze /start.")
    
    def handle_trigger_reevaluation(self, message: MatrixMessage):
        """Handle /trigger_reevaluation"""
        if not TEST_MODE and not PILOT_MODE:
            return
        
        phone_number = message.sender
        group = UserDataManager.get_user_group(phone_number)
        
        if not group:
            self.bot.send_message(phone_number, "Du bist noch nicht registriert.")
            return
        
        if phone_number in self.reevaluation_manager.pending_reevaluations:
            self.bot.send_message(phone_number, "Re-Evaluation läuft bereits.")
            return
        
        if self.reevaluation_manager.start_reevaluation(phone_number):
            logger.info(f"Manually triggered reevaluation for {phone_number}")
        else:
            self.bot.send_message(phone_number, "Re-Evaluation konnte nicht gestartet werden.")
    
    def handle_trigger_intervention(self, message: MatrixMessage):
        """Manually trigger intervention (TEST_MODE only)"""
        if not TEST_MODE and not PILOT_MODE:
            self.bot.send_message(message.sender, "Dieser Command ist nur im TEST_MODE verfügbar.")
            return
        
        phone_number = message.sender
        logger.info(f"Manually triggered intervention for {phone_number}")
        
        group = UserDataManager.get_user_group(phone_number)
        condition = "intervention"  # Force intervention
        
        if not group:
            self.bot.send_message(phone_number, "Bitte erst /start verwenden!")
            return
        
        success = self.intervention_manager.start_for_user(phone_number, group, condition)
        
        if success:
            self.bot.send_message(phone_number, f"✅ Intervention für {group}-Gruppe gestartet!")
        else:
            self.bot.send_message(phone_number, "⚠️ Konnte Intervention nicht starten (läuft bereits?)")
    

    def handle_advance_day(self, message: MatrixMessage):
        """Manually advance study day (TEST_MODE only)"""
        if not TEST_MODE and not PILOT_MODE:
            self.bot.send_message(message.sender, "Dieser Command ist nur im TEST_MODE verfügbar.")
            return
        
        phone_number = message.sender
        
        # Check if user exists
        group = UserDataManager.get_user_group(phone_number)
        if not group:
            self.bot.send_message(phone_number, "Bitte erst /start verwenden!")
            return
        
        # Advance day
        old_day = self.study_manager.get_study_day(phone_number)
        self.study_manager.advance_day_for_test(phone_number)
        new_day = self.study_manager.get_study_day(phone_number)
        
        # Add 1 point (for testing)
        user_state = UserState.load(phone_number)
        user_state.engagement_points += 1
        user_state.save()
        
        self.bot.send_message(
            phone_number,
            f"📅 Tag vorgerückt: Tag {old_day} → Tag {new_day}/10"
        )
        
        # Check if study should complete
        if new_day >= STUDY_DURATION_DAYS:
            self.bot.send_message(phone_number, "🎯 Tag 10 erreicht! Re-Assessment wird gestartet...")
            self.study_manager.check_and_complete_study(phone_number, self.reassessment_manager)
        
        logger.info(f"Advanced day for {phone_number}: {old_day} -> {new_day}")

    def handle_reset(self, message: MatrixMessage):
        """Reset user to start fresh (TEST_MODE/PILOT_MODE only)"""
        if not TEST_MODE and not PILOT_MODE:
            self.bot.send_message(message.sender, "Dieser Command ist nur im TEST/PILOT_MODE verfügbar.")
            return
        
        phone_number = message.sender
        logger.info(f"Reset requested by {phone_number}")
        
        try:
            # 1. Remove from user_data.txt
            user_data_file = os.path.join(DATA_DIR, 'user_data.txt')
            if os.path.exists(user_data_file):
                with open(user_data_file, 'r') as f:
                    lines = f.readlines()
                with open(user_data_file, 'w') as f:
                    for line in lines:
                        if phone_number not in line:
                            f.write(line)
            
            # 2. Remove user state file
            state_file = os.path.join(DATA_DIR, 'user_states', f'{phone_number}.json')
            if os.path.exists(state_file):
                os.remove(state_file)
            
            # 3. Remove from study_completed.txt
            completed_file = os.path.join(DATA_DIR, 'study_completed.txt')
            if os.path.exists(completed_file):
                with open(completed_file, 'r') as f:
                    lines = f.readlines()
                with open(completed_file, 'w') as f:
                    for line in lines:
                        if phone_number not in line:
                            f.write(line)
            
            # 4. Remove from internal caches
            if phone_number in self.study_manager.completed_users:
                self.study_manager.completed_users.remove(phone_number)
            if phone_number in self.subscription_manager.subscribers:
                self.subscription_manager.remove_subscriber(phone_number)
            if phone_number in self.onboarding_manager.onboarding_users:
                del self.onboarding_manager.onboarding_users[phone_number]
            if phone_number in self.reassessment_manager.reassessment_users:
                del self.reassessment_manager.reassessment_users[phone_number]
            
            self.bot.send_message(
                phone_number,
                "🔄 Dein Account wurde zurückgesetzt!\n\n"
                "Schreibe start um neu zu beginnen.",
                formatted_body=(
                    "🔄 Dein Account wurde zurückgesetzt!<br><br>"
                    "Schreibe <strong>start</strong> um neu zu beginnen."
                )
            )
            
            logger.info(f"User {phone_number} successfully reset")
            
        except Exception as e:
            logger.error(f"Error resetting user {phone_number}: {e}")
            self.bot.send_message(phone_number, "❌ Fehler beim Zurücksetzen. Bitte Admin kontaktieren.")
    def handle_message(self, message: MatrixMessage):
        """Main message handler"""
        phone_number = message.sender
        text = message.message.strip()
        
        logger.info(f"Message from {phone_number}: {text[:50]}...")
        

        # Android-friendly: Handle commands without slash
        text_lower = text.lower()
        if text_lower == 'start':
            self.handle_start(message)
            return
        if text_lower == 'help':
            self.handle_help(message)
            return
        if text_lower == 'stop':
            self.handle_stop(message)
            return
        if text_lower == 'info':
            self.handle_info(message)
            return
        if text_lower == 'progress':
            self.handle_progress(message)
            return
        if text_lower == 'trigger_intervention':
            self.handle_trigger_intervention(message)
            return
        if text_lower in ['bereit', 'ready', 'be'] and not self.intervention_manager.handle_message(phone_number, text):
            # Nur als Trigger wenn keine Intervention aktiv ist
            self.handle_trigger_intervention(message)
            return
        if text_lower == 'advance_day':
            self.handle_advance_day(message)
            return
        if text_lower == 'reset':
            self.handle_reset(message)
            return
        # Check if study completed
        if phone_number in self.study_manager.completed_users:
            self.bot.send_message(
                phone_number,
                f"Die Studie ist abgeschlossen.\n\n"
                f"Falls du die Umfrage noch nicht ausgefüllt hast:\n{SURVEY_URL}"
            )
            return
        
        # Crisis check
        if self._is_crisis_message(text):
            self._send_crisis_help(phone_number)
            return
        
        # Re-evaluation (highest priority)
        if self.reevaluation_manager.handle_message(phone_number, text):
            return
        

        # Re-assessment (post-study)
        if self.reassessment_manager.handle_message(phone_number, text):
            return
        # Onboarding
        if self.onboarding_manager.handle_message(phone_number, text):
            return
        
        # Interventions
        if self.intervention_manager.handle_message(phone_number, text):
            return
        
        # Default
        self.bot.send_message(
            phone_number,
            "Hi! Ich bin Ella.\n\nSchreibe start um zu beginnen oder help für Hilfe.",
            formatted_body="Hi! Ich bin Ella.<br><br>Schreibe <strong>start</strong> um zu beginnen oder <strong>help</strong> für Hilfe."
        )

    
    def _is_crisis_message(self, text: str) -> bool:
        """Check for crisis keywords"""
        crisis_keywords = [
            'suizid', 'suizidal', 'selbstmord', 'umbringen', 'tod', 'sterben',
            'nicht mehr leben', 'ende machen', 'aufgeben', 'hoffnungslos',
            'verzweifelt', 'kann nicht mehr', 'alles sinnlos'
        ]
        return any(keyword in text.lower() for keyword in crisis_keywords)
    
    def _send_crisis_help(self, phone_number: str):
        """Send crisis help"""
        help_text = """HILFE IN KRISEN

Sofortige Hilfe:
Telefonseelsorge: 0800 111 0 111 oder 0800 111 0 222 (24h)
Online: www.telefonseelsorge.de

Weitere Hilfe:
Notfall: 112
Ärztlicher Bereitschaftsdienst: 116 117
Nummer gegen Kummer: 0800 111 0 550

Du bist nicht allein! Professionelle Hilfe ist verfügbar.

Studienleitung: jakob.fink-lamotte@uni-potsdam.de"""
        
        self.bot.send_message(phone_number, help_text)
    
    def _setup_scheduler(self):
        """Setup scheduler for daily interventions"""
        if TEST_MODE:
            # Test mode: No automatic interventions - use /trigger_reevaluation or day-advance
            # Interventions triggered manually or after completing previous day
            logger.info("TEST_MODE: Manual intervention triggering only (use /trigger_reevaluation)")
        elif MULTI_TIME_TEST:
            # Multi-time test mode: Several times per day
            for test_time in TEST_TIMES:
                schedule.every().day.at(test_time).do(self._send_morning_interventions)
                logger.info(f"MULTI_TIME_TEST: Intervention geplant für {test_time}")
            schedule.every().day.at("00:01").do(self._check_study_completions)
        else:
            # Production: Daily at configured time
            schedule.every().day.at(MORNING_INTERVENTION_TIME).do(self._send_morning_interventions)
            schedule.every().day.at("00:01").do(self._check_study_completions)
            logger.info(f"Production: Intervention geplant für {MORNING_INTERVENTION_TIME}")
        
        scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        scheduler_thread.start()
    
    def _run_scheduler(self):
        """Run scheduler"""
        while True:
            schedule.run_pending()
            time.sleep(30)
    
    def _send_morning_interventions(self):
        """Send daily morning interventions"""
        logger.info("=== MORNING INTERVENTION CHECK ===")
        logger.info(f"Total subscribers: {len(self.subscription_manager.subscribers)}")
        
        for phone_number in list(self.subscription_manager.subscribers):
            try:
                logger.info(f"Checking {phone_number[:20]}...")
                
                # Skip if study completed
                if phone_number in self.study_manager.completed_users:
                    logger.info(f"  ❌ SKIP: Study completed")
                    continue
                
                # Skip if not in active study period
                if not self.study_manager.is_study_active(phone_number):
                    logger.info(f"  ❌ SKIP: Study not active")
                    continue
                
                # Skip if already had intervention today (aber nicht im TEST_MODE)
                if not TEST_MODE and not PILOT_MODE and self.study_manager.has_intervention_today(phone_number):
                    logger.info(f"  ❌ SKIP: Already had intervention today")
                    continue
                elif (TEST_MODE or PILOT_MODE) and self.study_manager.has_intervention_today(phone_number):
                    logger.info(f"  🧪 TEST_MODE: Skipping 'has_intervention_today' check - allowing multiple interventions")
                
                # Skip if re-evaluation pending
                if phone_number in self.reevaluation_manager.pending_reevaluations:
                    logger.info(f"  ⏳ SKIP: Re-evaluation pending")
                    continue
                
                # Check if re-evaluation due
                if self.reevaluation_manager.is_due(phone_number):
                    logger.info(f"  🔄 Starting re-evaluation")
                    self.reevaluation_manager.start_reevaluation(phone_number)
                    continue
                
                # Start daily intervention
                group = UserDataManager.get_user_group(phone_number)
                condition = UserDataManager.get_user_condition(phone_number)
                
                # TEST_MODE: Immer Interventionsbedingung verwenden
                if TEST_MODE:
                    condition = "intervention"
                    logger.info(f"  🧪 TEST_MODE: Forcing intervention condition")
                
                if not group:
                    logger.warning(f"  ❌ SKIP: No group assigned")
                    continue
                
                study_day = self.study_manager.get_study_day(phone_number)
                logger.info(f"  ✅ Sending intervention (Day {study_day}, Group: {group}, Condition: {condition})")
                
                # Send greeting with study day
                self.bot.send_message(
                    phone_number,
                    f"Guten Morgen!\n\nTag {study_day}/10 - Zeit für deine heutige Reflexionsübung.\n\nSchreibe bereit um die Übung zu starten.",
                    formatted_body=(
                        f"Guten Morgen!<br><br>"
                        f"Tag {study_day}/10 - Zeit für deine heutige Reflexionsübung.<br><br>"
                        f"Schreibe <strong>bereit</strong> um die Übung zu starten."
                    )
                )
                time.sleep(2)
                
                success = self.intervention_manager.start_for_user(phone_number, group, condition)
                if success:
                    logger.info(f"  ✅ SUCCESS: Intervention started")
                else:
                    logger.warning(f"  ⚠️ FAILED: Could not start intervention")
                
                # TEST_MODE: Verzögerung zwischen Nutzern, damit Nachrichten nacheinander kommen
                if (TEST_MODE or PILOT_MODE) and success:
                    logger.info(f"  ⏱️ Waiting 2 seconds before next user...")
                    time.sleep(2)
            
            except Exception as e:
                logger.error(f"  ❌ ERROR: {e}")
        
        logger.info("=== INTERVENTION CHECK COMPLETE ===")
    
    def _check_study_completions(self):
        """Check for users who completed 10 days"""
        logger.info("Checking for study completions")
        
        for phone_number in list(self.subscription_manager.subscribers):
            try:
                if self.study_manager.check_and_complete_study(phone_number, self.reassessment_manager):
                    # Remove from subscribers after completion
                    self.subscription_manager.remove_subscriber(phone_number)
                    logger.info(f"Study completed and user removed: {phone_number}")
            
            except Exception as e:
                logger.error(f"Error checking study completion for {phone_number}: {e}")
    
    def start(self):
        """Start bot"""
        logger.info("Starting Ella-Bot (Matrix) with 10-Day Study Protocol + Control Condition + ID-Code")
        
        logger.info("=== ELLA-BOT MATRIX SYSTEM STATUS ===")
        logger.info(f"Homeserver: {MATRIX_HOMESERVER}")
        logger.info(f"Bot User: {MATRIX_USER_ID}")
        logger.info(f"Study Duration: {STUDY_DURATION_DAYS} days")
        
        
        if TEST_MODE:
            logger.info("Mode: TEST_MODE - Manual triggering only")
        elif PILOT_MODE:
            logger.info("Mode: PILOT_MODE - Daily interventions at 09:00, NO control group")
        elif MULTI_TIME_TEST:
            logger.info(f"Mode: MULTI_TIME_TEST - Zeiten: {', '.join(TEST_TIMES)}")
        else:
            logger.info(f"Mode: PRODUCTION - Zeit: {MORNING_INTERVENTION_TIME}, WITH control group (50/50)")
        
        logger.info(f"Survey URL: {SURVEY_URL}")
        logger.info("All 5 intervention handlers + Control handler loaded")
        logger.info("Point-based re-evaluation active")
        logger.info("Randomization: See mode above")
        logger.info("ID-Code system active")
        logger.info("SYSTEM READY")
        logger.info("===============================")
        
        self.bot.start_polling()


if __name__ == "__main__":
    if not all([MATRIX_HOMESERVER, MATRIX_USER_ID, MATRIX_ACCESS_TOKEN]):
        logger.error("Matrix configuration incomplete. Set MATRIX_HOMESERVER, MATRIX_USER_ID, MATRIX_ACCESS_TOKEN")
        exit(1)
    
    bot = EllaChatBot()
    bot.start()
