from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Playwright, sync_playwright

from telegram_client import TelegramClient

LOGGER = logging.getLogger(__name__)
WALLAPOP_URL = "https://es.wallapop.com"
WALLAPOP_SEARCH_URL = "https://es.wallapop.com/search?keywords=mario+kart+nintendo+switch&category_id=24200&max_sale_price=25&order_by=newest"
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
PRIORITY_TOKEN_KEYS = ("accessToken", "access_token", "ACCESS_TOKEN")


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
        token = self._open_and_extract_token(interactive_login=False, url=WALLAPOP_SEARCH_URL)
        if token:
            return token

        self._telegram.send_message(
            "⚠️ No se pudo renovar token de Wallapop automáticamente."
        )
        return None

    def _open_and_extract_token(self, interactive_login: bool, url: str = WALLAPOP_URL) -> str | None:
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = self._open_persistent_context(playwright)
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=60000)

                if interactive_login and not self._headless:
                    LOGGER.info(
                        "Completa el login manual en la ventana de Chromium. Esperando 90 segundos..."
                    )
                    page.wait_for_timeout(90_000)
                else:
                    page.wait_for_timeout(5_000)

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

        self._dump_auth_debug(context=context, page=page)

        return None

    def _extract_from_cookies(self, context: BrowserContext) -> str | None:
        cookies = context.cookies()
        for preferred in PRIORITY_TOKEN_KEYS:
            for cookie in cookies:
                if cookie.get("name") != preferred:
                    continue
                token = self._extract_jwt(str(cookie.get("value", "")))
                if token:
                    LOGGER.info("Token extraído de cookie %s", preferred)
                    return token

        for cookie in cookies:
            name = str(cookie.get("name", ""))
            if not name or "token" not in name.lower() or "refresh" in name.lower():
                continue

            token = self._extract_jwt(str(cookie.get("value", "")))
            if token:
                LOGGER.info("Token extraído de cookie %s", name)
                return token
        return None

    def _extract_from_storage(self, page: Any) -> str | None:
        entries = self._collect_storage_entries(page)
        if entries is None:
            return None

        token = self._extract_from_storage_entries(entries)
        return token

    def _collect_storage_entries(self, page: Any) -> list[dict[str, Any]] | None:
        script = """
        () => {
          const candidates = [];
          for (const storage of [window.localStorage, window.sessionStorage]) {
            const storageName = storage === window.localStorage ? 'localStorage' : 'sessionStorage';
            for (let i = 0; i < storage.length; i++) {
              const key = storage.key(i);
              if (!key) continue;
              const value = storage.getItem(key);
              if (!value) continue;
              candidates.push({ storage: storageName, key, value });
            }
          }
          return candidates;
        }
        """
        try:
            return page.evaluate(script)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("No se pudo leer storage: %s", exc)
            return None

    def _extract_from_storage_entries(self, entries: list[dict[str, Any]]) -> str | None:
        for preferred in PRIORITY_TOKEN_KEYS:
            for entry in entries:
                if entry.get("key") != preferred:
                    continue
                token = self._extract_jwt(str(entry.get("value", "")))
                if token:
                    LOGGER.info("Token extraído de %s key %s", entry.get("storage"), preferred)
                    return token

        for entry in entries:
            key = str(entry.get("key", "")).lower()
            value = entry.get("value")
            if value is None:
                continue
            if "refresh" in key:
                continue

            raw = str(value)

            if "token" in key:
                token = self._extract_jwt(raw)
                if token:
                    LOGGER.info("Token extraído de %s key %s", entry.get("storage"), entry.get("key"))
                    return token

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw

            token = self._find_token_in_object(parsed)
            if token:
                LOGGER.info("Token extraído de %s key %s", entry.get("storage"), entry.get("key"))
                return token

        return None

    def _find_token_in_object(self, payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                if (
                    isinstance(key, str)
                    and "token" in key.lower()
                    and "refresh" not in key.lower()
                    and isinstance(value, str)
                ):
                    token = self._extract_jwt(value)
                    if token:
                        return token
                nested = self._find_token_in_object(value)
                if nested:
                    return nested
        elif isinstance(payload, list):
            for item in payload:
                nested = self._find_token_in_object(item)
                if nested:
                    return nested
        elif isinstance(payload, str):
            return self._extract_jwt(payload)
        return None

    def _extract_jwt(self, value: str) -> str | None:
        match = JWT_PATTERN.search(value)
        return match.group(0) if match else None

    def _dump_auth_debug(self, context: BrowserContext, page: Any) -> None:
        dump_path = Path("debug_auth_dump.json")
        entries = self._collect_storage_entries(page) or []
        payload = {
            "cookies": context.cookies(),
            "storage": entries,
        }
        dump_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.warning("No se encontró accessToken válido. Dump guardado en %s", dump_path)
