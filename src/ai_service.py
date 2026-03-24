#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Service für Demokratie-Chatbot
Refaktorierte Version von generate_question.py
"""

import os
import random
import logging
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from project root
load_dotenv()

class AIService:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()

        if self.provider == "mistral":
            self.api_key = os.getenv("MISTRAL_API_KEY")
            if not self.api_key:
                logger.error("MISTRAL_API_KEY not set in environment")
                raise ValueError("Mistral API key required")
            self.model = "mistral-large-latest"
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.mistral.ai/v1",
            )
        else:
            self.api_key = os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                logger.error("OPENAI_API_KEY not set in environment")
                raise ValueError("OpenAI API key required")
            self.model = "gpt-4o"
            self.client = OpenAI(
                api_key=self.api_key,
            )

        logger.info(f"AIService initialized with provider={self.provider}, model={self.model}")

    def _make_request(self, prompt: str, max_tokens: int = 150, temperature: float = 0.7) -> str:
        """Zentrale Methode für API-Anfragen"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"AI Service error ({self.provider}): {e}")
            return "Es tut mir leid, ich kann momentan keine Antwort generieren."
    
    def validate_problem(self, text: str) -> str:
        """Bestärkt die Problembeschreibung empathisch"""
        prompt = (
            f"Bestärke die folgende Problembeschreibung empathisch und verständnisvoll. "
            f"Zeige, dass das Problem nachvollziehbar ist, ohne zu bewerten oder zu bagatellisieren: {text}"
        )
        result = self._make_request(prompt, max_tokens=100, temperature=0.7)
        return result or "Danke für Deine Offenheit - das ist ein wichtiges Thema!"
    
    def paraphrase(self, text: str) -> str:
        """Paraphrasiert den Input empathisch und klar"""
        prompt = f"Paraphrasiere den Userinput empathisch und klar: {text}"
        result = self._make_request(prompt, max_tokens=60, temperature=0.7)
        return result or text
    
    def summarize_precontemplation(self, problem: str, solution: str, paraphrased_solution: str,
                                   pos_short: str, neg_short: str, pos_long: str, neg_long: str) -> str:
        """Fasst Precontemplation-Überlegungen zusammen"""
        prompt = (
            "Hier sind sieben Textausschnitte zu einem politischen Problem, einem passenden Lösungsvorschlag "
            "und verschiedenen Konsequenzen aus dem Lösungsvorschlag. Fasse diese sieben Gedanken in etwa "
            "drei klaren und wertschätzenden Sätzen zusammen, ohne die Eingaben wörtlich zu wiederholen. "
            "Formuliere es so, dass es Jugendliche zwischen 11 und 16 Jahren gut verstehen."
            "Nutze stattdessen eine flüssige, zusammenhängende Formulierung, die die persönliche Reflexion würdigt:\n\n"
            f"1. {problem}\n2. {solution}\n3. {paraphrased_solution}\n4. {pos_short}\n"
            f"5. {neg_short}\n6. {pos_long}\n7. {neg_long}\n"
        )
        result = self._make_request(prompt, max_tokens=150, temperature=0.7)
        return result or "Hier ist die Zusammenfassung deiner Überlegungen."
    
    def get_suggested_problem(self) -> str:
        """Generiert ein vorgeschlagenes Problem für User ohne eigene Probleme"""
        try:
            prompt = (
                "Nenne ein aktuelles, konkretes gesellschaftliches oder politisches Problem in Deutschland, "
                "das für Jugendliche zwischen 11 und 16 Jahren relevant und verständlich ist. "
                "Das Problem soll kontrovers diskutiert werden können und nicht zu komplex sein. "
                "Formuliere es als einen klaren, kurzen Satz. "
                "Beispielthemen: Klimawandel, Digitalisierung, Bildung, Gerechtigkeit, etc."
            )
            
            result = self._make_request(prompt, max_tokens=100, temperature=0.8)
            return result.strip() if result and len(result) > 10 else self._get_fallback_problem()
            
        except Exception as e:
            logger.error(f"Error generating suggested problem: {e}")
            return self._get_fallback_problem()
    
    def _get_fallback_problem(self) -> str:
        """Fallback-Probleme falls AI-Service nicht verfügbar"""
        fallback_problems = [
            "Zu viel Müll auf dem Schulhof",
            "Handyverbot in der Schule nervt", 
            "Zu wenig Fahrradwege in der Stadt",
            "Cafeteria-Essen schmeckt schlecht",
            "Zu wenig Grünflächen zum Chillen",
            "WLAN in der Schule ist zu langsam",
            "Klimawandel wird nicht ernst genommen",
            "Soziale Medien verstärken Mobbing",
            "Ungleichheit zwischen Arm und Reich"
        ]
        return random.choice(fallback_problems)
    
    def contemplate_story(self) -> str:
        """Generiert motivierende Geschichten für Contemplation-Phase"""
        perspektiven = [
            "aus der Sicht eines/einer Jugendlichen",
            "aus der Sicht eines/einer besten Freund/Freundin",
            "aus der Sicht eines Elternteils"
        ]
        
        prompt_templates = [
            "Du bist ein Coach mit Expertise in politischer Bildung für Jugendliche. Schreibe eine kurze, "
            "motivierende Geschichte (ca. 6 Sätze) {perspektive}, die in einer Diskussion oder einer Situation "
            "ambivalent war, ob sie ihre eigene Meinung überdenken und offener gegenüber anderen Meinungen zu sein. "
            "Die Geschichte soll zeigen, dass Ambivalenz normal ist und kleine Schritte zu mehr Offenheit helfen können. "
            "Sie soll motivierend und damit einen Fokus auf die positiven Konsequenzen der Ambivalenz und der Offenheit zeigen. "
            "Die Geschichte soll für Jugendliche zwischen der 6. und 10. Klasse, lebensnah und alltagsbezogen sein."
            "Formuliere es so, dass es Jugendliche zwischen 11 und 16 Jahren gut verstehen.",
            
            "Beschreibe eine Szene (ca. 6-10 Sätze), in der jemand überlegt, bei einem viel-diskutierten Thema "
            "offener zu sein. Die Geschichte soll zeigen, wie kleine Veränderungen möglich sind. "
            "Sie soll lebensnah und alltagsbezogen und {perspektive} erzählt werden."
        ]
        
        perspektive = random.choice(perspektiven)
        prompt = random.choice(prompt_templates).format(perspektive=perspektive)
        
        result = self._make_request(prompt, max_tokens=300, temperature=0.95)
        return result or "Hier könnte eine motivierende Geschichte stehen."
    
    def fake_dialog(self) -> str:
        """Generiert fiktive Streitdialoge für Preparation-Phase"""
        prompt = (
            "Schreibe einen kurzen, fiktiven Streitdialog zwischen zwei Jugendlichen "
            "über ein gesellschaftliches Thema (z.B. Klima, Migration, Gleichberechtigung, oder andere). "
            "Jede Redezeile soll mit einem Vornamen beginnen (z.B. Anna: ... / Ben: ...). "
            "Der Dialog soll 4 bis 6 Zeilen umfassen und typische Missverständnisse oder Vorurteile enthalten. "
            "Der Dialog ist dazu gedacht, dass Schüler eine der Rollen im Dialog übernehmen und die letzte "
            "Antwort selbst schreiben soll. Ziel der Intervention ist das Üben von Perspektivübernahme und "
            "die Förderung von Offenheit gegenüber anderen Meinungen."
            "Formuliere es so, dass es Jugendliche zwischen 11 und 16 Jahren gut verstehen."
        )
        
        result = self._make_request(prompt, max_tokens=300, temperature=0.9)
        return result or "Anna: ...\nBen: ... (Hier könnte Dein Streitgespräch stehen.)"
    
    def conflict_card(self) -> str:
        """Generiert Konfliktsituationen für Action-Phase"""
        prompt = (
            "Erfinde eine kurze, alltagsnahe Konfliktsituation zwischen zwei Menschen zu einem gesellschaftlichen Thema. "
            "Die Personen sollen unterschiedliche Meinungen haben, aber sich mögen und respektieren. "
            "Themen können beispielsweise Gender, Klima, Migration, sozialer Zusammenhalt, Gerechtigkeit, etc. sein. "
            "Beschreibe die Situation in 1-2 Sätzen. Die Situation sollte möglichst authentisch für Jugendliche sein."
            "Formuliere es so, dass es Jugendliche zwischen 11 und 16 Jahren gut verstehen."
        )
        
        result = self._make_request(prompt, max_tokens=120, temperature=0.8)
        return result or "Hier könnte eine Konfliktsituation stehen."
    
    def echo_statement(self) -> str:
        """Generiert polarisierende Aussagen für Echo-Übung"""
        prompt = (
            "Formuliere eine polarisierende, kontroverse Aussage zu einem gesellschaftlichen Thema, "
            "wie sie in einer Diskussion fallen könnte. Die Aussage soll klar eine Seite vertreten, "
            "aber nicht beleidigend sein."
            "Formuliere es so, dass es Jugendliche zwischen 11 und 16 Jahren gut verstehen."
        )
        
        result = self._make_request(prompt, max_tokens=120, temperature=0.8)
        return result or "Hier könnte eine polarisierende Aussage stehen."
    
    def generate_question_for_group(self, group: str) -> str:
        """Generiert gruppenspezifische Reflexionsfragen"""
        prompts = {
            "Precontemplation": (
                "Generiere eine Reflexionsfrage für Jugendliche die auch schon 11 jährige verstehen, die noch nicht bereit sind, "
                "ihre Meinungen zu überdenken. Die Frage soll zum Nachdenken anregen, ohne zu überfordern."
            ),
            "Contemplation": (
                "Generiere eine Reflexionsfrage für Jugendliche die auch schon 11 jährige verstehen, die ambivalent sind bezüglich "
                "der Offenheit gegenüber anderen Meinungen. Die Frage soll Vor- und Nachteile abwägen lassen."
            ),
            "Preparation": (
                "Generiere eine Reflexionsfrage für Jugendliche die auch schon 11 jährige verstehen, die sich vorgenommen haben, "
                "offener zu werden. Die Frage soll konkrete Schritte und Strategien erfragen."
            ),
            "Action": (
                "Generiere eine Reflexionsfrage für Jugendliche die auch schon 11 jährige verstehen, die bereits aktiv an ihrer "
                "Offenheit arbeiten. Die Frage soll Erfahrungen und Herausforderungen erfragen."
            ),
            "Maintenance": (
                "Generiere eine Reflexionsfrage für Jugendliche die auch schon 11 jährige verstehen, die bereits sehr offen sind. "
                "Die Frage soll helfen, diese Offenheit zu erhalten und anderen zu helfen."
            )
        }
        
        prompt = prompts.get(group, prompts["Contemplation"])
        result = self._make_request(prompt, max_tokens=150, temperature=0.8)
        return result or "Was denkst du über Offenheit in Diskussionen?"


# Convenience-Funktionen für Kompatibilität mit dem alten System
def validate_problem(text: str) -> str:
    service = AIService()
    return service.validate_problem(text)

def paraphrase(text: str) -> str:
    service = AIService()
    return service.paraphrase(text)

def summarize_precontemplation(problem: str, solution: str, paraphrased_solution: str,
                               pos_short: str, neg_short: str, pos_long: str, neg_long: str) -> str:
    service = AIService()
    return service.summarize_precontemplation(problem, solution, paraphrased_solution,
                                              pos_short, neg_short, pos_long, neg_long)

def contemplate_story() -> str:
    service = AIService()
    return service.contemplate_story()

def fakedialog() -> str:
    service = AIService()
    return service.fake_dialog()

def conflictcard() -> str:
    service = AIService()
    return service.conflict_card()

def echo() -> str:
    service = AIService()
    return service.echo_statement()

# Command-line Interface für Kompatibilität
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ai_service.py <function> [args...]")
        sys.exit(1)
    
    function = sys.argv[1]
    service = AIService()
    
    try:
        if function == "validate" and len(sys.argv) > 2:
            print(service.validate_problem(sys.argv[2]))
        elif function == "paraphrase" and len(sys.argv) > 2:
            print(service.paraphrase(sys.argv[2]))
        elif function == "summarize" and len(sys.argv) > 8:
            print(service.summarize_precontemplation(
                sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
                sys.argv[6], sys.argv[7], sys.argv[8]
            ))
        elif function == "contemplate_story":
            print(service.contemplate_story())
        elif function == "fakedialog":
            print(service.fake_dialog())
        elif function == "conflictcard":
            print(service.conflict_card())
        elif function == "echo":
            print(service.echo_statement())
        elif function in ["Precontemplation", "Contemplation", "Preparation", "Action", "Maintenance"]:
            print(service.generate_question_for_group(function))
        else:
            print(f"Unknown function: {function}")
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)