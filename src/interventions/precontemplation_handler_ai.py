#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Powered Precontemplation Handler v2.1 - IMPROVED
Max. 3 Interaktionen - Strukturierte 6-Schritt Reflexion

IMPROVEMENTS:
- IMMER Validierung + konkrete Frage (keine geschlossenen Aussagen)
- Klarere Struktur für Follow-up garantieren
"""

import logging
import json
from typing import Dict, Optional
from datetime import datetime
from ai_service import AIService
from user_state_points import UserState

logger = logging.getLogger(__name__)


class AIPrecontemplationHandler:
    """
    AI-gesteuerter Precontemplation Handler mit strukturierter 6-Schritt Reflexion
    
    Phase-Ziel: Bewusstsein für Offenheit fördern
    
    Techniken:
    - Motivational Interviewing (Validierung, Empathie)
    - Kognitive Umstrukturierung (Pro/Contra Analyse)
    - Sokratische Gesprächsführung
    
    Struktur (max. 3 Interaktionen):
    1. Problem erkennen + Emotionen erkunden
    2. Lösung entwickeln + erste Konsequenz
    3. Pro/Contra abschließen + Zusammenfassung
    """
    
    MAX_INTERACTIONS = 5  # Harte Grenze
    
    def __init__(self, bot_instance, study_manager=None):
        self.bot = bot_instance
        self.study_manager = study_manager
        self.ai = AIService()
        self.sessions: Dict[str, Dict] = {}
    

    def _clean_message(self, message: str) -> str:
        """Remove prompt structure markers from AI response to prevent leakage"""
        import re
        patterns = [
            r'[1-6]️⃣\s*\*{0,2}(VALIDIERUNG|FRAGE|BEISPIEL|ZUSAMMENFASSUNG|ABSCHLUSS|ÜBERLEITUNG)[:\*]*\s*',
            r'\*{2}(VALIDIERUNG|FRAGE|BEISPIEL|ZUSAMMENFASSUNG|ABSCHLUSS|ÜBERLEITUNG)\*{2}[:\s]*',
            r'\*\*(VALIDIERUNG|FRAGE|BEISPIEL|ZUSAMMENFASSUNG|ABSCHLUSS|ÜBERLEITUNG):\*\*\s*',
            r'\*\*(VALIDIERUNG|FRAGE|BEISPIEL|ZUSAMMENFASSUNG|ABSCHLUSS|ÜBERLEITUNG)\*\*:\s*',
            r'^(VALIDIERUNG|FRAGE|BEISPIEL|ZUSAMMENFASSUNG|ABSCHLUSS|ÜBERLEITUNG):\s*',
            r'^\*\*(VALIDIERUNG|FRAGE):\*\*\s*',
        ]
        for pattern in patterns:
            message = re.sub(pattern, '', message, flags=re.IGNORECASE | re.MULTILINE)
        message = re.sub(r'\n{3,}', '\n\n', message)
        message = re.sub(r' {2,}', ' ', message)
        return message.strip()

    def start_intervention(self, phone_number: str) -> bool:
        """Startet strukturierte 6-Schritt Reflexion"""
        if phone_number in self.sessions:
            logger.warning(f"Precontemplation already active for {phone_number}")
            return False
        
        user_state = UserState.load(phone_number)
        
        # AI generiert Opening für Schritt 1: Problem & Emotion
        opening = self._ai_generate_opening(user_state)
        
        # Initialisiere Session mit Interaktionszähler
        self.sessions[phone_number] = {
            "step": 1,  # Aktuelle Phase der 6-Schritt Reflexion
            "interaction_count": 0,  # Wie oft hat User geantwortet
            "start_time": datetime.now().isoformat(),
            "conversation": [],
            "opening_snippet": opening,
            "style_note": "",
            "data": {
                "problem": None,
                "emotions": None,
                "burden": None,
                "solution": None,
                "consequences_pro": [],
                "consequences_contra": []
            },
            "user_state_snapshot": {
                "level": user_state.level,
                "points": user_state.engagement_points
            }
        }
        
        # Sende Opening
        self.bot.send_message(phone_number, self._clean_message(opening))
        self._add_to_conversation(phone_number, "assistant", opening)
        
        return True
    
    def handle_message(self, phone_number: str, text: str) -> bool:
        """Verarbeitet User-Antwort mit striktem Interaktions-Limit"""
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
            
            # AI analysiert und steuert nächsten Schritt
            ai_decision = self._ai_process_response(phone_number, text, session)
            
            if ai_decision["action"] == "continue":
                # Weitermachen (nur wenn nicht am Limit)
                self.bot.send_message(phone_number, self._clean_message(ai_decision["message"]))
                self._add_to_conversation(phone_number, "assistant", ai_decision["message"])

                # Update Schritt wenn AI es vorschlägt
                if "next_step" in ai_decision:
                    session["step"] = ai_decision["next_step"]
                if ai_decision.get("style_note"):
                    session["style_note"] = ai_decision["style_note"]

            elif ai_decision["action"] == "need_help":
                # User braucht Hilfe - biete konkretes Beispiel
                help_message = self._ai_generate_help(phone_number, session)
                self.bot.send_message(phone_number, self._clean_message(help_message))
                self._add_to_conversation(phone_number, "assistant", help_message)

            elif ai_decision["action"] == "complete":
                # Vorzeitiger Abschluss (z.B. User hat alles gut beantwortet)
                if ai_decision.get("style_note"):
                    session["style_note"] = ai_decision["style_note"]
                self._complete_intervention(phone_number, ai_decision)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in Precontemplation: {e}")
            self._emergency_complete(phone_number)
            return False
    
    def _ai_generate_opening(self, user_state: UserState) -> str:
        """AI generiert Opening für Schritt 1: Problem & Emotion erkennen"""
        prompt = f"""Du bist ELLA, ein Coach für Jugendliche und junge Erwachsene (11-25 Jahre).
Starte eine Precontemplation-Intervention mit Fokus auf Bewusstsein für Offenheit fördern.

ZIEL VON SCHRITT 1:
User soll ein Problem erkennen, das ihn beschäftigt (politisch, gesellschaftlich, im Alltag).

USER-PROFIL:
- Level: {user_state.level}
- Punkte: {user_state.engagement_points}
- Phase: Precontemplation (noch kein Bewusstsein)

BISHERIGE INTERVENTIONS-HISTORY:
{user_state.get_history_summary()}
→ Wähle ein Einstiegsthema, das noch nicht verwendet wurde.

TECHNIKEN:
- Motivational Interviewing: Validierung, Empathie, offene Fragen
- Sokratische Gesprächsführung: Nachdenken anregen statt belehren

AUFGABE:
Formuliere eine einladende Eröffnung (1-2 Sätze), die:
- Fragt, ob etwas den User beschäftigt oder nervt
- Konkrete Beispiele gibt (Alltag, Nachrichten, in der Stadt, beim Lernen, in Gruppen)
- Niedrigschwellig und nicht wertend ist
- Jugendgerecht (11-25 Jahre)
- Mit KONKRETER FRAGE endet (nicht mit Aussage!)

WICHTIG:
- NIEMALS "Schule" oder "Studium" sagen - stattdessen: "beim Lernen", "im Alltag", "in Gruppen"
- Neugierig, nicht belehrend
- IMMER mit Fragezeichen enden!

Antworte NUR mit der Nachricht, kein JSON."""
        
        result = self.ai._make_request(prompt, max_tokens=200, temperature=0.7)
        return result or "Manchmal nerven uns Dinge im Alltag... Gibt es etwas, was dich gerade beschäftigt?"
    
    def _ai_process_response(self, phone_number: str, text: str, session: Dict) -> Dict:
        """AI analysiert Antwort und steuert durch die 6 Schritte der Reflexion"""
        
        conversation = self._format_conversation(session["conversation"])
        current_step = session["step"]
        interaction_count = session["interaction_count"]
        remaining = self.MAX_INTERACTIONS - interaction_count
        data = session["data"]
        
        prompt = f"""Du bist ELLA in einer strukturierten Precontemplation-Intervention (6-Schritt Reflexion).

**HARTER LIMIT: Nur noch {remaining} ELLA-Antworten möglich!**

TECHNIKEN:
- Motivational Interviewing (Validierung, Empathie)
- Kognitive Umstrukturierung (Pro/Contra)
- Sokratische Gesprächsführung

AKTUELLER SCHRITT: {current_step}/6
INTERAKTION: {interaction_count}/{self.MAX_INTERACTIONS}

6-SCHRITT STRUKTUR:
1. Problem benennen
2. Emotionen erkunden
3. Belastung einschätzen
4. Lösung entwickeln
5. Pro-Konsequenzen
6. Contra-Konsequenzen

GESAMMELTE DATEN:
- Problem: {data.get('problem', 'fehlt noch')}
- Emotionen: {data.get('emotions', 'fehlt noch')}
- Lösung: {data.get('solution', 'fehlt noch')}
- Pro-Konsequenzen: {len(data.get('consequences_pro', []))}
- Contra-Konsequenzen: {len(data.get('consequences_contra', []))}

DIALOG:
{conversation}

USER: "{text}"

**ENTSCHEIDUNGSLOGIK - STRIKT NACH INTERAKTIONSZAHL:**

**Interaktion 1 (gerade passiert):**
- Wenn Problem + Emotion genannt → CONTINUE zu Schritt 3-4 (Lösung)
- Wenn nur Problem → CONTINUE zu Schritt 2 (Emotion)
- Wenn kein Problem ("weiß nicht") → NEED_HELP (Beispiel anbieten)
- Wenn zu vage → CONTINUE mit konkreter Nachfrage

**Interaktion 2 (gerade passiert):**
- Wenn Problem + Emotion vollständig → CONTINUE zu Schritt 4 (Lösung)
- Wenn Emotion fehlt → CONTINUE: Gefühl nachfragen
- Wenn kein Problem → NEED_HELP (Beispiel anbieten)

**Interaktion 3 (gerade passiert):**
- Wenn Lösung genannt → CONTINUE zu Schritt 5 (Pro-Konsequenzen)
- Wenn keine Lösung → NEED_HELP (Lösungsideen mit Wahlmöglichkeiten)
- User MUSS spätestens jetzt eine Lösung haben!

**Interaktion 4 (gerade passiert):**
- Wenn Pro-Konsequenz vorhanden → CONTINUE zu Schritt 6 (Contra)
- Wenn keine Konsequenz → CONTINUE: Konsequenz konkret nachfragen
- Bleibe im Gesprächsfluss, kein Abschluss!

**Interaktion 5 (LETZTE - gerade passiert):**
- IMMER COMPLETE - egal was User sagt
- Sammle was gesagt wurde und schließe ab

**KRITISCH: STRUKTUR FÜR "CONTINUE"**

Deine Nachricht MUSS IMMER diese Struktur haben:
1️⃣ **VALIDIERUNG** (1 kurzer Satz)
   - Zeige dass du verstehst
   - Motivational Interviewing
   - Beispiel: "Das klingt echt anstrengend.", "Verstehe, das nervt."

2️⃣ **KONKRETE FRAGE** (1 Satz)
   - MIT Beispielen oder Wahlmöglichkeiten
   - User muss wissen WAS er antworten soll
   - Beispiele siehe unten

**NIEMALS:**
❌ Nur Validierung ohne Frage
❌ Geschlossene Aussage am Ende
❌ Vage Fragen ohne Beispiele

**IMMER:**
✅ Validierung + konkrete Frage
✅ Mit Fragezeichen enden
✅ Beispiele oder Wahlmöglichkeiten geben

**BEISPIELE FÜR GUTE "CONTINUE" NACHRICHTEN:**

Schritt 1→2 (Problem→Emotion):
"Das klingt wirklich nervig. Wie fühlt sich das für dich an - eher frustrierend, ärgerlich oder macht dich das traurig?"

Schritt 2→4 (Emotion→Lösung):
"Verstehe, das ist echt anstrengend. Was denkst du: Wer oder was könnte helfen - du selbst, andere Leute, oder müsste sich was im System ändern?"

Schritt 4→5 (Lösung→Pro):
"Gute Idee! Was wäre denn das Beste, was passieren könnte - sofort spürbar oder langfristig?"

Schritt 5→6 (Pro→Contra):
"Klingt gut! Aber mal ehrlich: Was könnte schwierig werden dabei - zu teuer, zu aufwendig, oder würden manche dagegen sein?"

VARIANZ-HINWEIS:
{UserState.load(phone_number).get_history_summary()}
→ Formuliere Validierung und Fragen anders als in den obigen Einstiegen.
→ Variiere: Satzstruktur, Beispiele, Fragestil (offen/Auswahl/hypothetisch).

PASSUNG VOR STRUKTUR:
Wenn der User etwas Persönliches oder Unerwartetes teilt, gehe darauf ein –
auch wenn das die 6-Schritt-Struktur unterbricht. Authentizität schlägt Plan.

WICHTIG:
- NIEMALS "Schule/Studium/Klasse" - stattdessen: "beim Lernen", "im Alltag", "in Gruppen"
- Max 2 Sätze (Validierung + Frage)
- Konkrete Beispiele oder Wahlmöglichkeiten
- Motivational Interviewing: validierend, empathisch
- Jugendgerecht (11-25 Jahre)

ANTWORT (JSON):
{{
    "action": "continue|need_help|complete",
    "message": "VALIDIERUNG + KONKRETE FRAGE (bei continue/need_help)",
    "next_step": 1-6,
    "data_update": {{"problem": "...", "emotions": "...", "solution": "...", "consequence_pro": "...", "consequence_contra": "..."}},
    "points": 1-3,
    "style_note": "Kurze Beschreibung deines Stils (z.B. 'humorvoll', 'direkt-fragend', 'empathisch-erzählend')",
    "reasoning": "Kurze Begründung"
}}
"""
        
        response = self.ai._make_request(prompt, max_tokens=400, temperature=0.7)
        parsed = self._parse_json(response, {
            "action": "complete",
            "message": "",
            "points": 1,
            "reasoning": "fallback"
        })
        
        # QUALITY CHECK: Bei "continue" muss Frage vorhanden sein
        if parsed["action"] == "continue":
            message = parsed.get("message", "")
            if not message or "?" not in message:
                logger.warning(f"AI response missing question mark, forcing need_help")
                parsed["action"] = "need_help"
        
        # Update session data falls AI es vorschlägt
        if "data_update" in parsed:
            for key, value in parsed["data_update"].items():
                if key.startswith("consequence_pro"):
                    session["data"]["consequences_pro"].append(value)
                elif key.startswith("consequence_contra"):
                    session["data"]["consequences_contra"].append(value)
                else:
                    session["data"][key] = value
        
        return parsed
    
    def _ai_generate_help(self, phone_number: str, session: Dict) -> str:
        """AI generiert konkrete Hilfe wenn User blockiert ist"""
        
        conversation = self._format_conversation(session["conversation"])
        current_step = session["step"]
        
        prompt = f"""User ist blockiert bei Schritt: {current_step}

DIALOG:
{conversation}

Generiere hilfreiche Nachricht mit Motivational Interviewing (Validierung + konkrete Frage).

**STRUKTUR (genau so):**
1️⃣ VALIDIERUNG (1 Satz): Zeige Verständnis
2️⃣ BEISPIEL (2-3 Bullet Points): Konkrete Wahlmöglichkeiten
3️⃣ FRAGE (1 Satz): Was passt? Oder war's was anderes?

**Falls Schritt 1-2 (Problem/Emotion):**
"Kein Problem, wenn dir gerade nichts einfällt. Hier ein paar Ideen:

• Angenommen, es nervt dich dass im Park überall Müll rumliegt
• Oder dass beim Lernen alle abgelenkt sind
• Oder dass in Gruppen niemand zuhört

Erkennst du dich da wieder? Oder war's was ganz anderes?"

**Falls Schritt 3-4 (Lösung):**
"Lösungen zu finden ist nicht immer einfach. Überleg mal:

• Könntest du selbst was tun?
• Könnten Freunde oder Familie helfen?
• Müsste die Stadt/Gemeinde was ändern?

Was würde am ehesten helfen?"

**Falls Schritt 5-6 (Konsequenzen):**
"Es ist gut, wenn du verschiedene Seiten siehst. Denk mal:

• Was wäre sofort besser?
• Was würde langfristig helfen?
• Aber was könnte schwierig werden?

Was fällt dir spontan ein?"

WICHTIG:
- NIEMALS "Schule/Studium/Klasse" - stattdessen: "beim Lernen", "im Alltag", "in Gruppen"
- Empathisch, nicht belehrend
- IMMER mit konkreten Beispielen (Bullet Points)
- IMMER mit Frage am Ende
- Jugendgerecht (11-25 Jahre)

Antworte NUR mit der Nachricht, kein JSON."""
        
        result = self.ai._make_request(prompt, max_tokens=250, temperature=0.7)
        
        # Fallback falls AI keine Frage generiert
        if not result or "?" not in result:
            return "Kein Problem! Was beschäftigt dich gerade am meisten - im Alltag, in Gruppen, oder wenn du Nachrichten siehst?"
        
        return result
    
    def _force_complete_intervention(self, phone_number: str, last_text: str):
        """Erzwingt Abschluss nach 3. Interaktion"""
        session = self.sessions[phone_number]
        
        # Versuche noch Daten aus letzter Antwort zu extrahieren
        self._extract_final_data(session, last_text)
        
        # Generiere Zusammenfassung
        summary = self._ai_generate_summary(session)
        self.bot.send_message(phone_number, self._clean_message(summary))
        
        # Points vergeben
        points = self._calculate_points(session)

        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(points, self.bot)

        # History-Eintrag
        user_state.add_intervention_to_history(
            day=user_state.last_evaluation_day,
            phase="Precontemplation",
            type="6-Schritt-Reflexion",
            topic=session["data"].get("problem", "unbekannt")[:60],
            opening_snippet=session.get("opening_snippet", ""),
            style_note=session.get("style_note", "")
        )

        # Daten speichern
        self._save_session_data(phone_number, session, points, summary)

        if self.study_manager:
            pass  # advance_day disabled - day advances by real time only

        # Cleanup
        del self.sessions[phone_number]
        logger.info(f"Precontemplation force-completed for {phone_number}: {points} points")
    
    def _complete_intervention(self, phone_number: str, ai_decision: Dict):
        """Schließt Intervention vorzeitig ab (wenn alles gut beantwortet)"""
        session = self.sessions[phone_number]
        
        # AI generiert Zusammenfassung
        summary = self._ai_generate_summary(session)
        self.bot.send_message(phone_number, self._clean_message(summary))
        
        # Points vergeben
        points = ai_decision.get("points", 2)
        points = self._calculate_points(session, base_points=points)

        user_state = UserState.load(phone_number)
        user_state.add_engagement_points(points, self.bot)

        # History-Eintrag
        user_state.add_intervention_to_history(
            day=user_state.last_evaluation_day,
            phase="Precontemplation",
            type="6-Schritt-Reflexion",
            topic=session["data"].get("problem", "unbekannt")[:60],
            opening_snippet=session.get("opening_snippet", ""),
            style_note=session.get("style_note", "")
        )

        # Daten speichern
        self._save_session_data(phone_number, session, points, summary)

        if self.study_manager:
            pass  # advance_day disabled - day advances by real time only

        # Cleanup
        del self.sessions[phone_number]
        logger.info(f"Precontemplation completed early for {phone_number}: {points} points")
    
    def _extract_final_data(self, session: Dict, text: str):
        """Versucht aus letzter Antwort noch Daten zu extrahieren"""
        current_step = session["step"]
        data = session["data"]
        
        # Einfache Heuristik basierend auf Schritt
        if current_step <= 2 and not data.get("problem"):
            data["problem"] = text[:100]
        elif current_step <= 4 and not data.get("solution"):
            data["solution"] = text[:100]
        elif current_step >= 5:
            # Versuche als Konsequenz zu interpretieren
            if "gut" in text.lower() or "besser" in text.lower():
                data["consequences_pro"].append(text[:100])
            else:
                data["consequences_contra"].append(text[:100])
    
    def _calculate_points(self, session: Dict, base_points: int = 1) -> int:
        """Berechnet Punkte basierend auf Vollständigkeit"""
        data = session["data"]
        points = base_points
        
        # +1 wenn Problem und Lösung vorhanden
        if data.get("problem") and data.get("solution"):
            points += 1
        
        # +1 wenn Pro UND Contra Konsequenzen
        if data.get("consequences_pro") and data.get("consequences_contra"):
            points += 1
        
        return min(points, 3)  # Max 3 Punkte
    
    def _ai_generate_summary(self, session: Dict) -> str:
        """AI generiert wertschätzende Zusammenfassung der 6-Schritt Reflexion"""
        
        conversation = self._format_conversation(session["conversation"])
        data = session["data"]
        
        prompt = f"""Erstelle eine wertschätzende Zusammenfassung dieser Precontemplation-Intervention (6-Schritt Reflexion).

TECHNIKEN:
- Motivational Interviewing (Validierung, nicht Lob)
- Kognitive Umstrukturierung (Pro/Contra würdigen)

GESAMMELTE DATEN:
- Problem: {data.get('problem', 'nicht vollständig')}
- Emotionen: {data.get('emotions', 'nicht vollständig')}
- Lösung: {data.get('solution', 'nicht vollständig')}
- Pro-Konsequenzen: {data.get('consequences_pro', [])}
- Contra-Konsequenzen: {data.get('consequences_contra', [])}

DIALOG:
{conversation}

ANFORDERUNGEN:
- Fasse die Reflexion zusammen (was User erkannt hat)
- Zeige Pro UND Contra (Ambivalenz ist wertvoll!)
- Würdige das Nachdenken (nicht "super gemacht!", sondern echte Wertschätzung)
- Motiviere subtil zur Offenheit
- 2-3 Sätze maximum
- Jugendgerecht (11-25 Jahre)

WICHTIG:
- NIEMALS "Schule/Studium/Klasse"
- Keine übertriebenen Lobpreisungen
- Validierung statt Bewertung
- KEINE Frage am Ende (Abschluss!)

STRUKTUR:
1. Problem/Lösung kurz benennen
2. Pro/Contra würdigen
3. Wertschätzung für Reflexion

Antworte NUR mit der Zusammenfassung, kein JSON."""
        
        result = self.ai._make_request(prompt, max_tokens=250, temperature=0.7)
        return result or "Danke, dass du dir Zeit zum Nachdenken genommen hast. Es ist wertvoll, verschiedene Seiten zu sehen. 💭"
    
    def _emergency_complete(self, phone_number: str):
        """Notfall-Abschluss bei Fehler"""
        self.bot.send_message(
            phone_number,
            "Danke für deine Gedanken! 💭"
        )
        
        if self.study_manager:
            pass  # advance_day disabled - day advances by real time only
            
        if phone_number in self.sessions:
            session = self.sessions[phone_number]
            self._save_session_data(phone_number, session, points=1, summary="Error", error=True)
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
    
    def _parse_json(self, response: str, fallback: Dict) -> Dict:
        """Parse JSON mit Fallback"""
        try:
            if "{" in response and "}" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
                # Robustness: trailing commas entfernen (Mistral-Eigenheit)
                import re
                json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
                return json.loads(json_str)
        except Exception as e:
            logger.warning(f"JSON parse failed in Precontemplation: {e}")
        return fallback
    
    def _save_session_data(self, phone_number: str, session: Dict, points: int, 
                          summary: str = "", error: bool = False):
        """Speichert Session-Daten"""
        try:
            filepath = "../data/precontemplation_ai_sessions_v2.jsonl"
            
            with open(filepath, "a", encoding="utf-8") as f:
                data = {
                    "timestamp": datetime.now().isoformat(),
                    "phone_number": phone_number,
                    "phase": "Precontemplation",
                    "version": "v2.1_always_question",
                    "duration_seconds": (
                        datetime.now() - datetime.fromisoformat(session["start_time"])
                    ).total_seconds(),
                    "final_step": session["step"],
                    "interaction_count": session["interaction_count"],
                    "points_awarded": points,
                    "conversation": session["conversation"],
                    "collected_data": session["data"],
                    "summary": summary,
                    "user_state": session["user_state_snapshot"],
                    "error": error
                }
                
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"Error saving Precontemplation data: {e}")
    
    # ===== STATUS METHODS =====
    
    def is_active(self, phone_number: str) -> bool:
        return phone_number in self.sessions
    
    def get_active_users(self) -> list:
        return list(self.sessions.keys())
    
    def get_session_info(self, phone_number: str) -> Optional[Dict]:
        return self.sessions.get(phone_number)


# ===== USAGE EXAMPLE =====

if __name__ == "__main__":
    """Test mit max 5 Interaktionen"""

    class MockBot:
        def send_message(self, recipient, message):
            print(f"\n📱 → {recipient[:20]}...")
            print(f"💬 {message}\n")

    handler = AIPrecontemplationHandler(MockBot())
    test_user = "+491234567890"

    print("=" * 70)
    print("TEST: Precontemplation Handler v2.2 (5 Interaktionen)")
    print("=" * 70)

    # Start
    print("\n1️⃣ ELLA startet Intervention...")
    handler.start_intervention(test_user)

    # Interaktion 1
    print("\n2️⃣ USER Interaktion 1/5: Problem nennen")
    handler.handle_message(test_user, "Mich nervt, dass im Park überall Müll rumliegt")

    # Interaktion 2
    print("\n3️⃣ USER Interaktion 2/5: Emotion")
    handler.handle_message(test_user, "Das macht mich echt traurig und wütend")

    # Interaktion 3
    print("\n4️⃣ USER Interaktion 3/5: Lösung")
    handler.handle_message(test_user, "Mehr Mülleimer aufstellen würde helfen")

    # Interaktion 4
    print("\n5️⃣ USER Interaktion 4/5: Pro-Konsequenz")
    handler.handle_message(test_user, "Es wäre sofort sauberer und schöner")

    # Interaktion 5 - LETZTE, wird abschließen
    print("\n6️⃣ USER Interaktion 5/5: Contra (FINALE)")
    handler.handle_message(test_user, "Aber das kostet Geld und manche werfen trotzdem Müll hin")

    print("\n✅ Test complete - genau 5 Interaktionen!")
