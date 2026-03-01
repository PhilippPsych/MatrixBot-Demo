#!/usr/bin/env python3
"""Matrix adapter backed by local Rust sidecar HTTP API."""

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class MatrixMessage:
    sender: str
    message: str
    timestamp: int
    room_id: str
    group_id: Optional[str] = None


class MatrixAdapter:
    def __init__(
        self,
        homeserver: str,
        user_id: str,
        access_token: str = None,
        sidecar_url: Optional[str] = None,
    ):
        self.homeserver = homeserver
        self.user_id = user_id
        self.access_token = access_token
        self.sidecar_url = sidecar_url or os.getenv(
            "MATRIX_SIDECAR_URL", "http://127.0.0.1:8010"
        )
        self.handlers: Dict[str, Callable] = {}
        self.user_rooms: Dict[str, str] = {}
        self.running = False
        self.poll_thread: Optional[threading.Thread] = None
        self._after_id = 0
        self._use_events_endpoint = True

    def add_handler(self, event_type: str, handler: Callable):
        self.handlers[event_type] = handler

    def send_message(self, recipient: str, message: str) -> bool:
        payload = {"recipient": recipient, "message": message}
        try:
            response = requests.post(
                f"{self.sidecar_url}/send",
                json=payload,
                timeout=30,
            )
            if response.status_code >= 400:
                logger.error(
                    "Failed to send to %s: status=%s body=%s",
                    recipient,
                    response.status_code,
                    response.text[:300],
                )
                return False

            result = response.json()
            ok = result.get("ok", result.get("success", False))
            if ok:
                logger.info("Message sent to %s", recipient)
                room_id = result.get("room_id")
                if room_id:
                    self.user_rooms[recipient] = room_id
                return True

            logger.error("Failed to send to %s: %s", recipient, result)
            return False
        except Exception as exc:
            logger.error("Error sending to %s: %s", recipient, exc)
            return False

    def _dispatch_message(self, matrix_msg: MatrixMessage):
        text = (matrix_msg.message or "").strip()
        if not text:
            return

        if text.startswith("/"):
            cmd = text.split()[0].lower()[1:]
            handler_key = f"command:{cmd}"
            handler = self.handlers.get(handler_key)
            if handler is not None:
                try:
                    handler(matrix_msg)
                except Exception as exc:
                    logger.error("Handler error for %s: %s", handler_key, exc)
                return

        handler = self.handlers.get("message")
        if handler is not None:
            try:
                handler(matrix_msg)
            except Exception as exc:
                logger.error("Handler error for message: %s", exc)

    def _poll_events_once(self) -> bool:
        params = {"after": self._after_id, "timeout_ms": 25000, "limit": 100}
        response = requests.get(
            f"{self.sidecar_url}/events",
            params=params,
            timeout=(5, 35),
        )

        if response.status_code == 404:
            return False
        response.raise_for_status()

        payload = response.json()
        events = payload.get("events", [])
        next_after = payload.get("next_after", self._after_id)

        for event in events:
            if event.get("type") != "message":
                continue
            sender = event.get("sender")
            if not sender or sender == self.user_id:
                continue

            body = event.get("message") or ""
            room_id = event.get("room_id", "")
            timestamp = int(event.get("timestamp") or int(time.time() * 1000))
            self.user_rooms[sender] = room_id

            logger.info("Received message from %s: %s...", sender, body[:50])
            self._dispatch_message(
                MatrixMessage(
                    sender=sender,
                    message=body,
                    timestamp=timestamp,
                    room_id=room_id,
                )
            )

        self._after_id = int(next_after)
        return True

    def _poll_legacy_messages_once(self):
        response = requests.get(f"{self.sidecar_url}/messages", timeout=5)
        response.raise_for_status()
        messages = response.json()
        for msg in messages:
            sender = msg.get("sender")
            if not sender or sender == self.user_id:
                continue
            body = msg.get("body") or ""
            room_id = msg.get("room_id") or ""
            self.user_rooms[sender] = room_id
            logger.info("Received message from %s: %s...", sender, body[:50])
            self._dispatch_message(
                MatrixMessage(
                    sender=sender,
                    message=body,
                    timestamp=int(time.time() * 1000),
                    room_id=room_id,
                )
            )

    def _poll_messages(self):
        while self.running:
            try:
                if self._use_events_endpoint:
                    if not self._poll_events_once():
                        logger.warning(
                            "Sidecar has no /events endpoint, falling back to legacy /messages"
                        )
                        self._use_events_endpoint = False
                        continue
                else:
                    self._poll_legacy_messages_once()
            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.ConnectionError as exc:
                logger.error("Poll connection error: %s", exc)
                time.sleep(1)
            except Exception as exc:
                logger.error("Poll error: %s", exc)
                time.sleep(0.5)

    def start(self):
        try:
            response = requests.get(f"{self.sidecar_url}/health", timeout=5)
            response.raise_for_status()
            health = response.json()
            logger.info(
                "Matrix client initialized for %s (device: %s)",
                health.get("user_id"),
                health.get("device_id"),
            )
        except Exception as exc:
            logger.error("Cannot connect to Sidecar at %s: %s", self.sidecar_url, exc)
            raise

        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_messages, daemon=True)
        self.poll_thread.start()
        logger.info("Matrix message receiver started")
        logger.info("Matrix Bot started successfully")

    def start_polling(self):
        if not self.running:
            self.start()
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        if self.poll_thread:
            self.poll_thread.join(timeout=2)
        logger.info("Matrix adapter stopped")


MatrixBot = MatrixAdapter
