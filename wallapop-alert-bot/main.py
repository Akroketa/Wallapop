from __future__ import annotations

import html
import logging
import time
from typing import Any

from config import load_config
from storage import SeenStorage
from telegram_client import TelegramClient
from token_manager import TokenManager
from wallapop_client import SearchFilters, UnauthorizedError, WallapopClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger("wallapop_alert_bot")



def _extract_item_id(item: dict[str, Any]) -> str | None:
    for key in ("id", "item_id", "web_slug"):
        value = item.get(key)
        if value:
            return str(value)
    return None



def _build_message(item: dict[str, Any]) -> str:
    title = html.escape(str(item.get("title") or "Sin título"))
    price_data = item.get("price") or {}
    price = price_data.get("amount") if isinstance(price_data, dict) else None
    currency = price_data.get("currency") if isinstance(price_data, dict) else "EUR"
    price_txt = f"{price} {currency}" if price is not None else "No disponible"

    description = item.get("description") or "Sin descripción"
    description = html.escape(str(description))
    short_description = description[:180] + ("..." if len(description) > 180 else "")

    url = item.get("web_slug")
    if url and not str(url).startswith("http"):
        link = f"https://es.wallapop.com/item/{url}"
    else:
        link = str(url) if url else "https://es.wallapop.com"

    return (
        "🎮 <b>Nuevo anuncio en Wallapop</b>\n\n"
        f"<b>{title}</b>\n"
        f"💶 {html.escape(price_txt)}\n"
        f"📝 {short_description}\n"
        f"🔗 {html.escape(link)}"
    )



def main() -> None:
    config = load_config()
    telegram = TelegramClient(config.telegram_token, config.telegram_chat_id)
    token_manager = TokenManager(config.wallapop_profile_dir, config.playwright_headless, telegram)
    storage = SeenStorage()
    client = WallapopClient()

    filters = SearchFilters(
        keywords=config.busqueda,
        max_sale_price=config.precio_maximo,
        category_id=config.categoria,
        latitude=config.latitude,
        longitude=config.longitude,
    )

    token = token_manager.get_token(interactive_login=True)
    if not token:
        LOGGER.error("No se puede continuar sin token.")
        return

    seen_ids = storage.load_seen_ids()

    try:
        initial_items = client.search(token, filters)
        for item in initial_items:
            item_id = _extract_item_id(item)
            if item_id:
                seen_ids.add(item_id)
        storage.save_seen_ids(seen_ids)
        LOGGER.info("Inicialización completa con %s anuncios ya vistos.", len(seen_ids))
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Error en búsqueda inicial: %s", exc)

    while True:
        try:
            items = client.search(token, filters)
        except UnauthorizedError:
            LOGGER.warning("Token caducado (401). Renovando...")
            token = token_manager.refresh_token() or ""
            if not token:
                telegram.send_message("⚠️ No se pudo renovar token tras 401 de Wallapop.")
                time.sleep(config.intervalo_segundos)
                continue

            try:
                items = client.search(token, filters)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Falló reintento tras renovar token: %s", exc)
                telegram.send_message("⚠️ Falló el reintento tras renovar token de Wallapop.")
                time.sleep(config.intervalo_segundos)
                continue
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Error consultando Wallapop: %s", exc)
            time.sleep(config.intervalo_segundos)
            continue

        new_count = 0
        for item in items:
            item_id = _extract_item_id(item)
            if not item_id or item_id in seen_ids:
                continue

            if telegram.send_message(_build_message(item)):
                new_count += 1
            seen_ids.add(item_id)

        if new_count:
            storage.save_seen_ids(seen_ids)
            LOGGER.info("Se notificaron %s anuncios nuevos.", new_count)
        else:
            LOGGER.info("Sin anuncios nuevos.")

        time.sleep(config.intervalo_segundos)


if __name__ == "__main__":
    main()
