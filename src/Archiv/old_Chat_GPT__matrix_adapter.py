#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Matrix REST API Adapter für Demokratie-Chatbot (Ella)

Spricht direkt mit der Matrix Client-Server API (/_matrix/client/v3/...).

Ziel:
- Gleiche Oberfläche wie SignalBot:
    - MatrixBot.send_message(recipient, text)
    - MatrixBot.add_handler("message", func)
    - MatrixBot.add_handler("command:start", func)
    - MatrixBot.start_polling()

Annahme:
- Es existiert bereits ein Bot-Account auf deinem Homeserver
- Wir nutzen ein Access-Token aus der Umgebung:
    MATRIX_HOMESERVER   z.B. "https://demokratiebot.de"
    MATRIX_ACCESS_TOKEN z.B. "syt_...."
"""

import requests
import json
import threading
import time
import logging
from typing import Dict, Callable, Optional, List
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)


@dataclass
class MatrixMessage:
    # WICHTIG: "sender" entspricht in deiner Bot-Logik der Konversations-ID.
    # Für Matrix nehmen wir dafür einfach die room_id des 1:1-Chats.
    sender: str          # room_id als eindeutige ID für die Person / den Chat
    message: str
    timestamp: int
    room_id: Optional[str] = None   # zur Klarheit explizit nochmal


class MatrixRestAdapter:
    """
    Sehr simple Matrix-Client-Implementierung:

    - pollt /_matrix/client/v3/sync in einer Schleife
    - extrahiert Textnachrichten aus beigetretenen Räumen
    - ruft deine Handler mit MatrixMessage auf
    - sendet Text mit /rooms/<room_id>/send/m.room.message/...
    """

    def __init__(self,
                 homeserver: str,
                 access_token: str):
        self.homeserver = homeserver.rstrip("/")
        self.access_token = access_token
        self.message_handlers: Dict[str, Callable] = {}
        self.command_handlers: Dict[str, Callable] = {}
        self.running = False
        self.receive_thread: Optional[threading.Thread] = None
        self.next_batch: Optional[str] = None

        # HTTP-Session
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        })

    # -----------------------
    # Handler-Registrierung
    # -----------------------

    def add_message_handler(self, handler: Callable[[MatrixMessage], None]):
        """Standard-Handler für eingehende Textnachrichten"""
        self.message_handlers["text"] = handler

    def add_command_handler(self, command: str, handler: Callable[[MatrixMessage], None]):
        """Handler für /kommandos"""
        self.command_handlers[command] = handler

    # -----------------------
    # Senden
    # -----------------------

    def send_message(self, room_id: str, message: str) -> bool:
        """
        Sendet eine Textnachricht in einen Raum.

        In deiner Bot-Logik entspricht "recipient" einfach dieser room_id.
        """
        try:
            # einfache Transaction-ID
            txn_id = str(int(time.time() * 1000))

            url = (
                f"{self.homeserver}"
                f"/_matrix/client/v3/rooms/{room_id}/send/"
                f"m.room.message/{txn_id}"
            )

            payload = {
                "msgtype": "m.text",
                "body": message,
            }

            resp = self.session.put(url, data=json.dumps(payload), timeout=30)

            if 200 <= resp.status_code < 300:
                logger.info(f"Matrix: sent message to {room_id}: {message[:50]}...")
                return True
            else:
                logger.error(
                    f"Matrix: failed to send message to {room_id}: "
                    f"{resp.status_code} - {resp.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Matrix: network error sending message to {room_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Matrix: unexpected error sending message: {e}")
            return False

    # -----------------------
    # Empfangen
    # -----------------------

    def start_receiving(self):
        """Startet Polling-/Sync-Schleife in separatem Thread"""
        if self.running:
            logger.warning("Matrix receiver already running")
            return

        self.running = True
        self.receive_thread = threading.Thread(
            target=self._sync_loop,
            daemon=True
        )
        self.receive_thread.start()
        logger.info("Matrix sync loop started")

    def stop_receiving(self):
        """Stoppt das Empfangen"""
        self.running = False
        if self.receive_thread:
            self.receive_thread.join(timeout=5)
        self.session.close()
        logger.info("Matrix receiver stopped")

    def _sync_loop(self):
        """
        Pollt /sync in einer Schleife.
        Siehe Matrix-Spezifikation: Client-Server API – /sync
        https://spec.matrix.org/
        """
        while self.running:
            try:
                params = {
                    "timeout": "30000",   # 30s long-polling
                }
                if self.next_batch:
                    params["since"] = self.next_batch

                url = f"{self.homeserver}/_matrix/client/v3/sync"
                resp = self.session.get(url, params=params, timeout=35)

                if resp.status_code == 200:
                    data = resp.json()
                    self.next_batch = data.get("next_batch", self.next_batch)
                    self._process_sync_response(data)
                else:
                    logger.warning(
                        f"Matrix sync error: {resp.status_code} - {resp.text}"
                    )

                # kleine Pause, damit wir bei Fehlern nicht tight loopen
                time.sleep(1)

            except requests.exceptions.Timeout:
                logger.debug("Matrix sync timeout – retrying")
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f"Matrix sync network error: {e}")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Matrix sync unexpected error: {e}")
                time.sleep(5)

    def _process_sync_response(self, data: Dict):
        """
        Extrahiert Textnachrichten aus join-Räumen und ruft Handler auf.
        Erwartete Struktur: data["rooms"]["join"][room_id]["timeline"]["events"]
        """

        rooms = data.get("rooms", {}).get("join", {})
        for room_id, room_data in rooms.items():
            events = room_data.get("timeline", {}).get("events", [])
            for ev in events:
                if ev.get("type") != "m.room.message":
                    continue

                content = ev.get("content", {})
                if content.get("msgtype") != "m.text":
                    continue

                body = content.get("body")
                if not body:
                    continue

                sender_mxid = ev.get("sender")
                ts = ev.get("origin_server_ts", int(time.time() * 1000))

                msg = MatrixMessage(
                    sender=room_id,      # unsere "User-ID" ist die room_id
                    message=body,
                    timestamp=ts,
                    room_id=room_id
                )

                self._handle_message(msg, sender_mxid=sender_mxid)

    def _handle_message(self, message: MatrixMessage, sender_mxid: Optional[str] = None):
        """
        Verteilt Nachrichten an Command- oder Standard-Handler.
        Deine restliche Bot-Logik erwartet nur .sender und .message.
        """
        if not message.message:
            return

        logger.info(
            f"Matrix: received message in {message.room_id} "
            f"(internal sender={message.sender}): {message.message[:50]}..."
        )

        text = message.message

        # Kommandos wie /start, /help, ...
        if text.startswith("/"):
            command = text.split()[0][1:]
            handler = self.command_handlers.get(command)
            if handler:
                try:
                    handler(message)
                except Exception as e:
                    logger.error(
                        f"Error in command handler '{command}': {e}"
                    )
            return

        # Standard-Handler
        handler = self.message_handlers.get("text")
        if handler:
            try:
                handler(message)
            except Exception as e:
                logger.error(f"Error in message handler: {e}")

    # -----------------------
    # Healthcheck
    # -----------------------

    def is_running(self) -> bool:
        return self.running and self.receive_thread and self.receive_thread.is_alive()

    def health_check(self) -> bool:
        """
        Einfacher Healthcheck: /_matrix/client/versions
        """
        try:
            url = f"{self.homeserver}/_matrix/client/versions"
            resp = self.session.get(url, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


# Convenience-Klasse wie SignalBot
class MatrixBot:
    def __init__(self,
                 homeserver: Optional[str] = None,
                 access_token: Optional[str] = None):
        """
        homeserver: z.B. "https://demokratiebot.de"
        access_token: Bot-Access-Token (aus Umgebungsvariable empfohlen)
        """
        if homeserver is None:
            homeserver = os.getenv("MATRIX_HOMESERVER", "").strip()
        if access_token is None:
            access_token = os.getenv("MATRIX_ACCESS_TOKEN", "").strip()

        if not homeserver or not access_token:
            logger.error(
                "MatrixBot: MATRIX_HOMESERVER oder MATRIX_ACCESS_TOKEN fehlen!"
            )

        self.adapter = MatrixRestAdapter(homeserver, access_token)

    def send_message(self, recipient: str, message: str) -> bool:
        # recipient == room_id
        return self.adapter.send_message(recipient, message)

    def add_handler(self, handler_type: str, handler_func: Callable):
        if handler_type == "message":
            self.adapter.add_message_handler(handler_func)
        elif handler_type.startswith("command:"):
            command = handler_type.split(":", 1)[1]
            self.adapter.add_command_handler(command, handler_func)

    def start_polling(self):
        if not self.adapter.health_check():
            logger.error("Matrix homeserver not reachable or /versions failed")
            return False

        self.adapter.start_receiving()
        logger.info("MatrixBot started successfully")

        try:
            while True:
                if not self.adapter.is_running():
                    logger.error("Matrix receiver stopped unexpectedly")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("MatrixBot stopped by user")
        finally:
            self.stop()

    def stop(self):
        self.adapter.stop_receiving()
        logger.info("MatrixBot stopped")


# Kleiner Test, optional
def test_api_connection():
    bot = MatrixBot()
    if not bot.adapter.health_check():
        print("❌ MATRIX_HOMESERVER oder Token scheinen nicht zu funktionieren.")
    else:
        print("✅ Homeserver antwortet auf /_matrix/client/versions")


if __name__ == "__main__":
    test_api_connection()
