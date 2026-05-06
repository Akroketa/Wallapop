from __future__ import annotations

import json
import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class SeenStorage:
    def __init__(self, file_path: str = "anuncios_vistos.json") -> None:
        self._path = Path(file_path)

    def load_seen_ids(self) -> set[str]:
        if not self._path.exists():
            return set()

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                LOGGER.warning("Formato inesperado en %s; reiniciando almacenamiento", self._path)
                return set()
            return {str(item) for item in data}
        except (json.JSONDecodeError, OSError) as exc:
            LOGGER.warning("No se pudo cargar %s (%s). Se reinicia estado.", self._path, exc)
            return set()

    def save_seen_ids(self, ids: set[str]) -> None:
        ordered = sorted(ids)
        self._path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
