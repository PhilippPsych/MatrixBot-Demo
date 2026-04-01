#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Matrix Adapter für Demokratie-Chatbot (Ella-Bot)
Ersetzt signal_rest_adapter.py für Matrix/Synapse

Verwendet matrix-nio (async) Library
"""

import asyncio
import logging
import time
import threading
from typing import Dict, Callable, Optional
from dataclasses import dataclass

from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessage,
    RoomMessageText,
    MegolmEvent,
    InviteEvent,
    LoginResponse,
    SyncResponse,
)

# Disable matrix-nio validation warnings
import logging as nio_logging
nio_logging.getLogger("nio").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


@dataclass
class MatrixMessage:
    """Nachrichtenformat - kompatibel mit SignalMessage"""
    sender: str          # Matrix User ID (z.B. @user:demokratiebot.de)
    message: str         # Nachrichtentext
    timestamp: int       # Unix timestamp in ms
    room_id: str         # Matrix Room ID
    group_id: Optional[str] = None  # Für Kompatibilität mit Signal-Code


class MatrixAdapter:
    """
    Matrix Client Adapter - ersetzt SignalRestAdapter
    
    Verwendet matrix-nio für async Kommunikation mit Synapse Homeserver.
    """
    
    def __init__(self, homeserver: str, user_id: str, access_token: str):
        """
        Args:
            homeserver: Matrix Homeserver URL (z.B. https://demokratiebot.de)
            user_id: Bot User ID (z.B. @ella:demokratiebot.de)
            access_token: Access Token für Authentication
        """
        self.homeserver = homeserver
        self.user_id = user_id
        self.access_token = access_token
        
        # Matrix Client
        self.client: Optional[AsyncClient] = None
        
        # Handler Storage
        self.message_handlers: Dict[str, Callable] = {}
        self.command_handlers: Dict[str, Callable] = {}
        
        # Room Management: user_id -> room_id mapping
        self.user_rooms: Dict[str, str] = {}
        
        # State
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.sync_thread: Optional[threading.Thread] = None
        
        # Duplikat-Schutz
        self.start_timestamp = int(time.time() * 1000)
        # Toleranz für Clock-Skew zwischen HS/Host
        self.start_skew_tolerance_ms = 5 * 60 * 1000
        self.processed_events: set = set()
        
    def add_message_handler(self, handler: Callable[[MatrixMessage], None]):
        """Fügt einen Handler für eingehende Nachrichten hinzu"""
        self.message_handlers['text'] = handler
        
    def add_command_handler(self, command: str, handler: Callable[[MatrixMessage], None]):
        """Fügt einen Handler für spezifische Kommandos hinzu"""
        self.command_handlers[command] = handler
    
    def send_message(self, recipient: str, message: str) -> bool:
        """
        Sendet eine Nachricht an einen User.
        
        Args:
            recipient: Matrix User ID (z.B. @user:demokratiebot.de)
            message: Nachrichtentext
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self.loop or not self.client:
            logger.error("Matrix client not initialized")
            return False
        
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._async_send_message(recipient, message),
                self.loop
            )
            return future.result(timeout=15)
        except Exception as e:
            logger.error(f"Error sending message to {recipient}: {e!r}")
            return False
    
    async def _async_send_message(self, recipient: str, message: str) -> bool:
        """Async Implementierung von send_message"""
        try:
            # Finde oder erstelle Direct Message Room
            room_id = await self._get_or_create_dm_room(recipient)
            
            if not room_id:
                logger.error(f"Could not get/create room for {recipient}")
                return False
            
            # Nachricht senden
            # Convert markdown bold (**text**) to HTML
            import re
            html_message = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', message)
            
            # Nachricht senden mit HTML-Formatierung
            content = {
                "msgtype": "m.text",
                "body": message
            }
            
            # Add HTML format if there's formatting
            if html_message != message:
                content["format"] = "org.matrix.custom.html"
                content["formatted_body"] = html_message.replace('\n', '<br>')
            
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content
            )
            
            if hasattr(response, 'event_id'):
                logger.info(f"Message sent to {recipient}: {message[:50]}...")
                return True
            else:
                logger.error(f"Failed to send message: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Error in _async_send_message: {e}")
            return False
    
    async def _get_or_create_dm_room(self, user_id: str) -> Optional[str]:
        """Findet existierenden DM-Room oder erstellt neuen"""
        
        # Check Cache
        if user_id in self.user_rooms:
            return self.user_rooms[user_id]
        
        # Suche existierenden DM-Room
        for room_id, room in self.client.rooms.items():
            # DM-Room: nur 2 Mitglieder (Bot + User)
            if len(room.users) == 2 and user_id in [u for u in room.users]:
                self.user_rooms[user_id] = room_id
                logger.info(f"Found existing DM room for {user_id}: {room_id}")
                return room_id
        
        # Erstelle neuen DM-Room
        try:
            response = await self.client.room_create(
                is_direct=True,
                invite=[user_id],
                name=None,  # DM-Rooms brauchen keinen Namen
                preset="trusted_private_chat"
            )
            
            if hasattr(response, 'room_id'):
                room_id = response.room_id
                self.user_rooms[user_id] = room_id
                logger.info(f"Created new DM room for {user_id}: {room_id}")
                return room_id
            else:
                logger.error(f"Failed to create room: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating DM room for {user_id}: {e}")
            return None
    
    def start_receiving(self):
        """Startet das Empfangen von Nachrichten in separatem Thread"""
        if self.running:
            logger.warning("Matrix receiver already running")
            return
        
        self.running = True
        self.sync_thread = threading.Thread(target=self._run_sync_loop, daemon=True)
        self.sync_thread.start()
        logger.info("Matrix message receiver started")
    
    def _run_sync_loop(self):
        """Führt den async Event Loop in separatem Thread aus — mit Auto-Restart"""
        max_restarts = 50
        for attempt in range(max_restarts):
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self._async_sync_loop())
                if not self.running:
                    logger.info("Sync loop stopped gracefully.")
                    break
            except BaseException as e:
                logger.error(f"Sync loop CRASHED (attempt {attempt+1}): {type(e).__name__}: {e}")
            finally:
                self.loop.close()

            if not self.running:
                break
            wait = min(30, 5 * (attempt + 1))
            logger.warning(f"Restarting sync loop in {wait}s (attempt {attempt+1}/{max_restarts})...")
            time.sleep(wait)
        else:
            logger.error("Sync loop exceeded max restarts. Giving up.")
    
    async def _async_sync_loop(self):
        """Hauptschleife für Matrix Sync"""
        
        # Client initialisieren
        self.client = AsyncClient(self.homeserver, self.user_id)
        self.client.access_token = self.access_token
        self.client.user_id = self.user_id
        
        # Event Callbacks registrieren
        # Catch all room message variants (text/notice/formatted/etc.)
        self.client.add_event_callback(self._on_message, RoomMessage)
        self.client.add_event_callback(self._on_megolm_event, MegolmEvent)
        self.client.add_event_callback(self._on_invite, InviteEvent)
        
        logger.info(f"Matrix client initialized for {self.user_id}")
        
        # Skip initial sync to avoid startup stalls behind pantalaimon.
        logger.info("Skipping initial sync, starting live sync loop...")
        
        # Continuous Sync Loop
        sync_count = 0
        while self.running:
            try:
                sync_count += 1
                if sync_count <= 3 or sync_count % 60 == 0:
                    logger.info(f"Sync #{sync_count} starting...")
                sync_response = await self.client.sync(timeout=5000)
                if not isinstance(sync_response, SyncResponse):
                    logger.error(f"Sync returned non-success response: {sync_response}")
                    # Prevent tight error loops on invalid/expired tokens.
                    if "M_UNKNOWN_TOKEN" in str(sync_response):
                        logger.error("Access token is invalid. Stopping sync loop.")
                        self.running = False
                        break
                    await asyncio.sleep(1)
                elif sync_count <= 3:
                    logger.info(f"Sync #{sync_count} OK - rooms: {len(sync_response.rooms.join)}, invited: {len(sync_response.rooms.invite)}")
            except BaseException as e:
                logger.error(f"Sync error ({type(e).__name__}): {e}")
                if isinstance(e, Exception):
                    await asyncio.sleep(5)
                else:
                    raise

        logger.error(f"Sync loop exited after {sync_count} syncs. running={self.running}")
        # Cleanup
        await self.client.close()
    
    async def _on_message(self, room: MatrixRoom, event: RoomMessage):
        """Callback für eingehende Nachrichten"""
        
        # Ignoriere eigene Nachrichten
        if event.sender == self.user_id:
            return

        # Alte Timeline-Events verwerfen, damit der Bot nicht im Backlog hängt.
        event_ts = getattr(event, "server_timestamp", 0) or 0
        if event_ts < (self.start_timestamp - self.start_skew_tolerance_ms):
            return
        
        # Ignoriere Duplikate
        if event.event_id in self.processed_events:
            return
        self.processed_events.add(event.event_id)
        
        message_text = getattr(event, "body", None)
        if not message_text:
            return
        sender = event.sender
        
        logger.info(f"Received message from {sender}: {message_text[:50]}...")
        
        # Cache Room für User
        self.user_rooms[sender] = room.room_id
        
        # MatrixMessage erstellen
        matrix_message = MatrixMessage(
            sender=sender,
            message=message_text,
            timestamp=event.server_timestamp,
            room_id=room.room_id
        )
        
        # Handler in worker thread ausführen, damit der nio event loop nicht blockiert.
        try:
            await asyncio.to_thread(self._handle_message_sync, matrix_message)
        except Exception as e:
            logger.error(f"Error handling message from {sender}: {e}")

    async def _on_megolm_event(self, room: MatrixRoom, event: MegolmEvent):
        """Callback für verschlüsselte Events, die nio nicht entschlüsseln konnte."""
        if event.sender == self.user_id:
            return
        logger.warning(
            "Received encrypted event (not decrypted) from %s in %s (event_id=%s)",
            event.sender,
            room.room_id,
            getattr(event, "event_id", "unknown"),
        )
    
    def _handle_message_sync(self, message: MatrixMessage):
        """Synchroner Message Handler (wird aus async context aufgerufen)"""
        if not message.message:
            return
        
        # Prüfe auf Kommandos
        if message.message.startswith('/'):
            parts = message.message.split()
            command = parts[0][1:]  # Entferne '/'
            
            if command in self.command_handlers:
                try:
                    self.command_handlers[command](message)
                except Exception as e:
                    logger.error(f"Error in command handler for '{command}': {e}")
                return
        
        # Standard Message Handler
        if 'text' in self.message_handlers:
            try:
                self.message_handlers['text'](message)
            except Exception as e:
                logger.error(f"Error in message handler: {e}")
    
    async def _on_invite(self, room: MatrixRoom, event: InviteEvent):
        """Callback für Raum-Einladungen - automatisch annehmen"""
        logger.info(f"Received invite to room {room.room_id} from {event.sender}")
        
        try:
            await self.client.join(room.room_id)
            logger.info(f"Joined room {room.room_id}")
            
            # Cache Room für User
            self.user_rooms[event.sender] = room.room_id
        except Exception as e:
            logger.error(f"Failed to join room {room.room_id}: {e}")
    
    def stop_receiving(self):
        """Stoppt das Empfangen von Nachrichten"""
        self.running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=5)
        logger.info("Matrix message receiver stopped")
    
    def is_running(self) -> bool:
        """Prüft ob der Receiver läuft"""
        return self.running and self.sync_thread and self.sync_thread.is_alive()
    
    def health_check(self) -> bool:
        """Prüft ob der Matrix Server erreichbar ist"""
        import requests
        try:
            response = requests.get(
                f"{self.homeserver}/_matrix/client/versions",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False


class MatrixBot:
    """
    Convenience-Klasse für einfache Migration von SignalBot.
    
    Hat dieselbe API wie SignalBot aus signal_rest_adapter.py
    """
    
    def __init__(self, homeserver: str, user_id: str, access_token: str):
        """
        Args:
            homeserver: Matrix Homeserver URL (z.B. https://demokratiebot.de)
            user_id: Bot User ID (z.B. @ella:demokratiebot.de)
            access_token: Access Token für Authentication
        """
        self.adapter = MatrixAdapter(homeserver, user_id, access_token)
        self.user_data = {}
    
    def send_message(self, recipient: str, message: str) -> bool:
        """Sendet eine Nachricht an einen User"""
        return self.adapter.send_message(recipient, message)
    
    def add_handler(self, handler_type: str, handler_func: Callable):
        """
        Registriert Handler - kompatibel mit SignalBot API.
        
        Args:
            handler_type: "message" oder "command:xyz"
            handler_func: Callback-Funktion
        """
        if handler_type == "message":
            self.adapter.add_message_handler(handler_func)
        elif handler_type.startswith("command:"):
            command = handler_type.split(":", 1)[1]
            self.adapter.add_command_handler(command, handler_func)
    
    def start_polling(self):
        """Startet den Bot"""
        # Health Check vor Start
        if not self.adapter.health_check():
            logger.error("Matrix server not reachable!")
            return False
        
        self.adapter.start_receiving()
        logger.info("Matrix Bot started successfully")
        
        try:
            while True:
                if not self.adapter.is_running():
                    logger.error("Matrix receiver stopped unexpectedly")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            self.stop()
    
    def stop(self):
        """Stoppt den Bot"""
        self.adapter.stop_receiving()
        logger.info("Matrix Bot stopped")


# ===== TEST FUNKTIONEN =====

def test_connection(homeserver: str, user_id: str, access_token: str):
    """Testet die Verbindung zum Matrix Server"""
    print(f"Testing connection to {homeserver}...")
    
    adapter = MatrixAdapter(homeserver, user_id, access_token)
    
    if adapter.health_check():
        print("✅ Matrix server is reachable")
        print(f"✅ User: {user_id}")
    else:
        print("❌ Matrix server not reachable")
        print("Check if homeserver URL is correct")


if __name__ == "__main__":
    import sys
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    homeserver = os.getenv("MATRIX_HOMESERVER")
    user_id = os.getenv("MATRIX_USER_ID")
    access_token = os.getenv("MATRIX_ACCESS_TOKEN")
    
    if not all([homeserver, user_id, access_token]):
        print("Please set MATRIX_HOMESERVER, MATRIX_USER_ID, MATRIX_ACCESS_TOKEN in .env")
        sys.exit(1)
    
    test_connection(homeserver, user_id, access_token)
