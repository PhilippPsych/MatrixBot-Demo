#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced UserState with Engagement Points System
"""

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

@dataclass
class UserState:
    """User state with engagement tracking"""
    user_id: str
    phase: str = "waiting"
    group: Optional[str] = None
    start_date: Optional[str] = None
    last_evaluation_day: int = 0
    pending_reevaluation: bool = False
    
    # Gamification
    engagement_points: int = 0
    total_interventions: int = 0
    last_intervention_date: Optional[str] = None
    level: int = 1
    reevaluation_count: int = 0
    intervention_history: List[Dict] = field(default_factory=list)

    def save(self):
        """Save state to file with thread safety"""
        file_path = f"../data/user_states/{self.user_id}.json"
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(self), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving user state for {self.user_id}: {e}")
    
    @classmethod
    def load(cls, user_id: str) -> 'UserState':
        """Load state from file"""
        file_path = f"../data/user_states/{user_id}.json"
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return cls(**data)
        except Exception as e:
            logger.error(f"Error loading user state for {user_id}: {e}")
        
        return cls(user_id=user_id)
    
    def add_engagement_points(self, points: int, bot_instance=None):
        """Add engagement points and check for level up"""
        old_points = self.engagement_points
        self.engagement_points += 1  # Always 1 point per intervention
        self.total_interventions += 1
        
        # Check for level up (every 10 points)
        old_level = self.level
        self.level = (self.engagement_points // 10) + 1
        
        self.save()
        
        # Send feedback if bot instance provided
        if bot_instance:
            self._send_point_feedback(bot_instance, points, old_level)
    
    def _send_point_feedback(self, bot, points: int, old_level: int):
        """Send engaging feedback about points"""
        message = f"✅ +1 Punkt! "
        
        # Add progress
        points_to_next = 10 - (self.engagement_points % 10)
        message += f"({self.engagement_points} Punkte gesamt"
        
        if points_to_next > 0:
            message += f", noch {points_to_next} bis zur nächsten Re-Evaluation"
        
        message += ")"
        
        # Level up notification
        if self.level > old_level:
            message += f"\n\n🎉 Level {self.level} erreicht!"
        
        bot.send_message(self.user_id, message)
    
    def needs_reevaluation(self) -> bool:
        """Check if user needs re-evaluation (every 10 points)"""
        if self.pending_reevaluation:
            return False
        
        # Re-evaluate every 10 points
        if self.engagement_points >= 10 and (self.engagement_points % 10) == 0:
            # Only if not done yet at this point level
            expected_reevals = self.engagement_points // 10
            return self.reevaluation_count < expected_reevals
        
        return False
    
    def mark_reevaluation_done(self):
        """Mark current re-evaluation as completed"""
        self.reevaluation_count += 1
        self.pending_reevaluation = False
        self.save()
    
    def add_intervention_to_history(self, day: int, phase: str, type: str, topic: str,
                                     opening_snippet: str = "", style_note: str = ""):
        """Fügt abgeschlossene Intervention zur History hinzu"""
        from datetime import date
        self.intervention_history.append({
            "date": date.today().isoformat(),
            "day": day,
            "phase": phase,
            "type": type,
            "topic": topic,
            "opening_snippet": opening_snippet[:100] if opening_snippet else "",
            "style_note": style_note
        })
        self.save()

    def get_history_summary(self) -> str:
        """Gibt lesbare Zusammenfassung der letzten Interventionen zurück"""
        if not self.intervention_history:
            return "Noch keine Interventionen."
        lines = []
        for e in self.intervention_history[-5:]:
            line = f"Tag {e['day']}: {e['type']} ({e['phase']}) – Thema: {e['topic']}"
            if e.get("opening_snippet"):
                line += f"\n  → Einstieg war: \"{e['opening_snippet']}...\""
            if e.get("style_note"):
                line += f"\n  → Stil: {e['style_note']}"
            lines.append(line)
        return "\n".join(lines)

    def get_progress_message(self) -> str:
        """Get user's progress overview"""
        points_to_next = 10 - (self.engagement_points % 10)
        
        return (
            f"📊 Dein Fortschritt:\n\n"
            f"Level: {self.level}\n"
            f"Punkte: {self.engagement_points}\n"
            f"Interventionen: {self.total_interventions}\n"
            f"Gruppe: {self.group}\n\n"
            f"Noch {points_to_next} Punkte bis zur nächsten Re-Evaluation!"
        )
