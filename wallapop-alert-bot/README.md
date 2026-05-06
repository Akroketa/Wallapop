# wallapop-alert-bot

Bot en Python que busca anuncios nuevos en Wallapop y envía alertas a Telegram cuando aparecen productos que cumplen filtros configurables.

## Características

- Búsqueda periódica en Wallapop (ordenado por más recientes).
- Filtros por texto, categoría, precio máximo y ubicación.
- Persistencia de anuncios vistos en `anuncios_vistos.json` para evitar duplicados.
- Envío de avisos por Telegram con formato HTML.
- Gestión de sesión/token con Playwright + Chromium **sin depender de navegador local**.
- Contexto persistente para mantener login entre ejecuciones.
- Preparado para local, Linux y Docker.

## Requisitos

- Python 3.11+
- Dependencias de `requirements.txt`

## Instalación local

```bash
cd wallapop-alert-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Configuración

1. Copia variables de ejemplo:

```bash
cp .env.example .env
```

2. Completa `.env` con tu token/chat de Telegram.

## Primer login de Wallapop (obligatorio)

Para guardar la sesión en el contexto persistente:

1. En `.env`, deja `PLAYWRIGHT_HEADLESS=false`.
2. Ejecuta el bot:

```bash
python main.py
```

3. Se abrirá Chromium gestionado por Playwright.
4. Inicia sesión manualmente en Wallapop.
5. Espera ~90 segundos para que el bot intente extraer token y persistir sesión.

> En ejecuciones posteriores, el bot reutilizará el perfil en `WALLAPOP_PROFILE_DIR`.

## Ejecución

```bash
python main.py
```

## Docker

### Construir y ejecutar

```bash
docker compose up --build -d
```

### Ver logs

```bash
docker compose logs -f
```

## Flujo del bot

1. Carga configuración desde `.env`.
2. Inicializa Telegram.
3. Obtiene token inicial de Wallapop con `TokenManager`.
4. Hace primera búsqueda y marca los anuncios actuales como vistos (sin avisar).
5. Entra en bucle cada `INTERVALO_SEGUNDOS`.
6. Si detecta anuncio nuevo, envía Telegram y guarda ID como visto.
7. Si la API devuelve 401, intenta renovar token y reintenta una vez.

## Variables soportadas

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `BUSQUEDA`
- `PRECIO_MAXIMO`
- `CATEGORIA`
- `LATITUDE`
- `LONGITUDE`
- `INTERVALO_SEGUNDOS`
- `PLAYWRIGHT_HEADLESS`
- `WALLAPOP_PROFILE_DIR`

## Notas

- No se hardcodean secretos.
- No usa Selenium, undetected_chromedriver ni Brave.
- Chromium se instala y gestiona con Playwright.
