from __future__ import annotations

import logging

import requests

LOGGER = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, token: str, chat_id: str, timeout: int = 15) -> None:
        self._chat_id = chat_id
        self._timeout = timeout
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send_message(self, text: str) -> bool:
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            response = requests.post(self._url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            body = response.json()
            if not body.get("ok", False):
                LOGGER.error("Telegram devolvió error lógico: %s", body)
                return False
            return True
        except requests.RequestException as exc:
            LOGGER.exception("Error enviando mensaje a Telegram: %s", exc)
            return False
