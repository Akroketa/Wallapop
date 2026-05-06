from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Playwright, sync_playwright

from telegram_client import TelegramClient

LOGGER = logging.getLogger(__name__)
WALLAPOP_URL = "https://es.wallapop.com"


class TokenManager:
    def __init__(self, profile_dir: str, headless: bool, telegram: TelegramClient) -> None:
        self._profile_dir = Path(profile_dir)
        self._headless = headless
        self._telegram = telegram

    def get_token(self, interactive_login: bool = False) -> str | None:
        token = self._open_and_extract_token(interactive_login=interactive_login)
        if token:
            return token

        LOGGER.error("No se encontró token de Wallapop.")
        self._telegram.send_message(
            "⚠️ No se pudo obtener el token de Wallapop. Revisa el login en el perfil persistente."
        )
        return None

    def refresh_token(self) -> str | None:
        LOGGER.info("Intentando renovar token de Wallapop...")
        token = self._open_and_extract_token(interactive_login=False)
        if token:
            return token

        self._telegram.send_message(
            "⚠️ No se pudo renovar token de Wallapop automáticamente."
        )
        return None

    def _open_and_extract_token(self, interactive_login: bool) -> str | None:
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = self._open_persistent_context(playwright)
            try:
                page = context.new_page()
                page.goto(WALLAPOP_URL, wait_until="domcontentloaded", timeout=60000)

                if interactive_login and not self._headless:
                    LOGGER.info(
                        "Completa el login manual en la ventana de Chromium. Esperando 90 segundos..."
                    )
                    page.wait_for_timeout(90_000)
                else:
                    page.wait_for_timeout(3_000)

                token = self._extract_token(context=context, page=page)
                return token
            finally:
                context.close()

    def _open_persistent_context(self, playwright: Playwright) -> BrowserContext:
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir),
            headless=self._headless,
            viewport={"width": 1366, "height": 768},
        )

    def _extract_token(self, context: BrowserContext, page: Any) -> str | None:
        token = self._extract_from_cookies(context)
        if token:
            return token

        token = self._extract_from_storage(page)
        if token:
            return token

        return None

    def _extract_from_cookies(self, context: BrowserContext) -> str | None:
        for cookie in context.cookies():
            if "token" in cookie.get("name", "").lower() and cookie.get("value"):
                return cookie["value"]
        return None

    def _extract_from_storage(self, page: Any) -> str | None:
        script = """
        () => {
          const candidates = [];
          for (const storage of [window.localStorage, window.sessionStorage]) {
            for (let i = 0; i < storage.length; i++) {
              const key = storage.key(i);
              if (!key) continue;
              const value = storage.getItem(key);
              if (!value) continue;
              candidates.push({ key, value });
            }
          }
          return candidates;
        }
        """
        try:
            entries = page.evaluate(script)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("No se pudo leer storage: %s", exc)
            return None

        for entry in entries:
            key = str(entry.get("key", "")).lower()
            value = entry.get("value")
            if value is None:
                continue
            if "token" in key:
                return str(value)

            raw = str(value)
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw

            token = self._find_token_in_object(parsed)
            if token:
                return token

        return None

    def _find_token_in_object(self, payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(key, str) and "token" in key.lower() and isinstance(value, str):
                    return value
                nested = self._find_token_in_object(value)
                if nested:
                    return nested
        elif isinstance(payload, list):
            for item in payload:
                nested = self._find_token_in_object(item)
                if nested:
                    return nested
        elif isinstance(payload, str) and payload.count(".") >= 2 and len(payload) > 20:
            return payload
        return None
