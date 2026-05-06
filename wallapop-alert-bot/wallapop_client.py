from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
API_URL = "https://api.wallapop.com/api/v3/search/section"


class UnauthorizedError(Exception):
    pass


@dataclass(slots=True)
class SearchFilters:
    keywords: str
    max_sale_price: int
    category_id: str
    latitude: float
    longitude: float


class WallapopClient:
    def __init__(self, timeout: int = 20) -> None:
        self._timeout = timeout

    def search(self, token: str, filters: SearchFilters) -> list[dict[str, Any]]:
        params = {
            "keywords": filters.keywords,
            "source": "deep_link",
            "order_by": "newest",
            "max_sale_price": str(filters.max_sale_price),
            "category_id": filters.category_id,
            "section_type": "organic_search_results",
            "latitude": str(filters.latitude),
            "longitude": str(filters.longitude),
            "time_filter": "today",
        }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Origin": "https://es.wallapop.com",
            "Referer": "https://es.wallapop.com/",
            "authorization": f"Bearer {token}",
            "x-appversion": "79316",
            "x-deviceid": "wallapop-alert-bot",
            "x-deviceos": "0",
        }

        response = requests.get(API_URL, params=params, headers=headers, timeout=self._timeout)
        if response.status_code == 401:
            raise UnauthorizedError("Token inválido o caducado")
        response.raise_for_status()

        payload = response.json()
        items = payload.get("data", {}).get("section", {}).get("payload", {}).get("items", [])
        if not isinstance(items, list):
            LOGGER.warning("Formato inesperado en respuesta de Wallapop")
            return []
        return items
