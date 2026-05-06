from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Config:
    telegram_token: str
    telegram_chat_id: str
    busqueda: str
    precio_maximo: int
    categoria: str
    latitude: float
    longitude: float
    intervalo_segundos: int
    playwright_headless: bool
    wallapop_profile_dir: str



def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}



def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Falta variable obligatoria: {name}")
    return value



def load_config() -> Config:
    load_dotenv()

    return Config(
        telegram_token=_require_env("TELEGRAM_TOKEN"),
        telegram_chat_id=_require_env("TELEGRAM_CHAT_ID"),
        busqueda=_require_env("BUSQUEDA"),
        precio_maximo=int(_require_env("PRECIO_MAXIMO")),
        categoria=_require_env("CATEGORIA"),
        latitude=float(_require_env("LATITUDE")),
        longitude=float(_require_env("LONGITUDE")),
        intervalo_segundos=int(_require_env("INTERVALO_SEGUNDOS")),
        playwright_headless=_parse_bool(os.getenv("PLAYWRIGHT_HEADLESS", "false")),
        wallapop_profile_dir=os.getenv("WALLAPOP_PROFILE_DIR", ".wallapop_profile"),
    )
