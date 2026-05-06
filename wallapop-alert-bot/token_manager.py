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
WALLAPOP_SEARCH_URL = (
    "https://es.wallapop.com/search?keywords=mario+kart+nintendo+switch"
    "&category_id=24200&max_sale_price=25&order_by=newest"
)
TOKEN_KEYS_PRIORITY = ("accessToken", "access_token", "ACCESS_TOKEN")
JWT_REGEX = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


class TokenManager:
    def __init__(self, profile_dir: str, headless: bool, telegram: TelegramClient) -> None:
        self._profile_dir = Path(profile_dir)
        self._headless = headless
        self._telegram = telegram

    def get_token(self, interactive_login: bool = False) -> str | None:
        token = self._open_and_extract_token(interactive_login=interactive_login, refresh_mode=False)
        if token:
            return token

        LOGGER.error("No se encontró token de Wallapop.")
        self._telegram.send_message(
            "⚠️ No se pudo obtener el token de Wallapop. Revisa el login en el perfil persistente."
        )
        return None

    def refresh_token(self) -> str | None:
        LOGGER.info("Intentando renovar token de Wallapop...")
        token = self._open_and_extract_token(interactive_login=False, refresh_mode=True)
        if token:
            return token

        self._telegram.send_message("⚠️ No se pudo renovar token de Wallapop automáticamente.")
        return None

    def _open_and_extract_token(self, interactive_login: bool, refresh_mode: bool) -> str | None:
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = self._open_persistent_context(playwright)
            try:
                page = context.new_page()
                target_url = WALLAPOP_SEARCH_URL if refresh_mode else WALLAPOP_URL
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=60000)

                if interactive_login and not self._headless:
                    LOGGER.info(
                        "Completa el login manual en la ventana de Chromium. Esperando 90 segundos..."
                    )
                    page.wait_for_timeout(90_000)
                else:
                    page.wait_for_timeout(5_000)

                token = self._extract_token(context=context, page=page)
                if not token:
                    self._write_debug_dump(context=context, page=page)
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

        token = self._extract_from_storage(page, storage_name="localStorage")
        if token:
            return token

        token = self._extract_from_storage(page, storage_name="sessionStorage")
        if token:
            return token

        return None

    def _extract_from_cookies(self, context: BrowserContext) -> str | None:
        cookies = context.cookies()

        for key in TOKEN_KEYS_PRIORITY:
            cookie = next((c for c in cookies if c.get("name") == key), None)
            if not cookie:
                continue
            token = self._extract_valid_access_token(cookie.get("value", ""), source=f"cookie {key}")
            if token:
                return token

        for cookie in cookies:
            name = str(cookie.get("name", ""))
            lower_name = name.lower()
            if "refreshtoken" in lower_name or lower_name == "refresh_token":
                continue
            if "token" not in lower_name:
                continue
            token = self._extract_valid_access_token(cookie.get("value", ""), source=f"cookie {name}")
            if token:
                return token

        return None

    def _extract_from_storage(self, page: Any, storage_name: str) -> str | None:
        script = """
        (storageName) => {
          const storage = storageName === "localStorage" ? window.localStorage : window.sessionStorage;
          const entries = [];
          for (let i = 0; i < storage.length; i++) {
            const key = storage.key(i);
            if (!key) continue;
            const value = storage.getItem(key);
            if (value === null) continue;
            entries.push({ key, value });
          }
          return entries;
        }
        """
        try:
            entries = page.evaluate(script, storage_name)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("No se pudo leer %s: %s", storage_name, exc)
            return None

        for key in TOKEN_KEYS_PRIORITY:
            exact_entry = next((e for e in entries if e.get("key") == key), None)
            if exact_entry:
                token = self._extract_valid_access_token(
                    exact_entry.get("value", ""), source=f"{storage_name} key {key}"
                )
                if token:
                    return token

        for entry in entries:
            key = str(entry.get("key", ""))
            low_key = key.lower()
            if "refreshtoken" in low_key or low_key == "refresh_token":
                continue
            if "token" not in low_key:
                continue

            token = self._extract_valid_access_token(
                entry.get("value", ""), source=f"{storage_name} key {key}"
            )
            if token:
                return token

        return None

    def _extract_valid_access_token(self, raw_value: Any, source: str) -> str | None:
        if raw_value is None:
            return None

        candidates = self._collect_string_candidates(raw_value)
        for candidate in candidates:
            if "refreshtoken" in candidate.lower() and not JWT_REGEX.search(candidate):
                continue

            match = JWT_REGEX.search(candidate)
            if not match:
                continue

            token = match.group(0)
            if self._is_jwt(token):
                LOGGER.info("Token extraído desde %s", source)
                return token

        return None

    def _collect_string_candidates(self, raw_value: Any) -> list[str]:
        output: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)
            elif isinstance(value, str):
                output.append(value)
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    return
                walk(parsed)

        walk(raw_value)
        if isinstance(raw_value, str):
            output.append(raw_value)
        return output

    def _is_jwt(self, token: str) -> bool:
        return bool(JWT_REGEX.fullmatch(token))

    def _write_debug_dump(self, context: BrowserContext, page: Any) -> None:
        dump_path = Path("debug_auth_dump.json")
        dump: dict[str, Any] = {"cookies": context.cookies(), "localStorage": {}, "sessionStorage": {}}
        for storage_name in ("localStorage", "sessionStorage"):
            script = """
            (storageName) => {
              const storage = storageName === "localStorage" ? window.localStorage : window.sessionStorage;
              const out = {};
              for (let i = 0; i < storage.length; i++) {
                const key = storage.key(i);
                if (!key) continue;
                out[key] = storage.getItem(key);
              }
              return out;
            }
            """
            try:
                dump[storage_name] = page.evaluate(script, storage_name)
            except Exception as exc:  # noqa: BLE001
                dump[storage_name] = {"_error": str(exc)}

        dump_path.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.warning("No se encontró accessToken válido. Dump guardado en %s", dump_path)
