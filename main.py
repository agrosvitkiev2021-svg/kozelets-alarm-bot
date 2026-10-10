import os
import json
import math
import hashlib
import html
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
import feedparser


# ============================================================
# KOZELETS ALARM BOT
# GITHUB ACTIONS VERSION
# ============================================================

print("=" * 70)
print("🤖 KOZELETS ALARM BOT")
print("=" * 70)
print(datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
print("=" * 70)


# ============================================================
# НАЛАШТУВАННЯ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")

# Ваш особистий юзернейм для кнопки «Запропонувати новину»
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Kasper081297").replace("@", "").strip()

# Офіційний API "Повітряна тривога"
AIR_API_TOKEN = os.getenv("AIR_API_TOKEN")

STATE_FILE = Path("bot_state.json")


if not BOT_TOKEN:
    raise RuntimeError("❌ Не знайдено BOT_TOKEN у GitHub Secrets")

if not CHANNEL:
    raise RuntimeError("❌ Не знайдено CHANNEL у GitHub Secrets")

if not AIR_API_TOKEN:
    raise RuntimeError("❌ Не знайдено AIR_API_TOKEN у GitHub Secrets")


# ============================================================
# ІНТЕРВАЛИ
# ============================================================

# NEPTUN — перевірка кожні 5 хвилин
NEPTUN_CHECK_SECONDS = 5 * 60

# Повторне повідомлення про активну загрозу
THREAT_UPDATE_SECONDS = 5 * 60

# Новини — кожні 30 хвилин
NEWS_CHECK_SECONDS = 30 * 60

# Брати тільки новини не старші 30 хвилин
NEWS_MAX_AGE_MINUTES = 30

# Погода — раз на 4 години
WEATHER_CHECK_SECONDS = 4 * 60 * 60

# Промо — раз на 6 годин
PROMO_CHECK_SECONDS = 6 * 60 * 60

# Історія / Цікаві факти про Козелеччину — раз на 12 годин
HISTORY_CHECK_SECONDS = 12 * 60 * 60

# Вечірній дайджест — раз на добу
DIGEST_CHECK_SECONDS = 24 * 60 * 60


# ============================================================
# ОФІЦІЙНИЙ API ПОВІТРЯНОЇ ТРИВОГИ
# ============================================================

AIR_API_URL = "https://api.ukrainealarm.com/api/v3/alerts/140"

# 140 — Чернігівський район
AIR_REGION_ID = 140

AIR_REGION_NAME = "Чернігівський район"


# ============================================================
# NEPTUN
# ============================================================

NEPTUN_API = "https://neptun.in.ua/api/v1/threats"
NEPTUN_URL = "https://neptun.in.ua/"


# ============================================================
# НАСЕЛЕНІ ПУНКТИ
# ============================================================

PLACES = {
    "Козелець": (50.913, 31.121),
    "Остер": (50.950, 30.883),
    "Кіпті": (51.050, 31.150),
    "Чемер": (51.108, 31.216),
    "Десна": (50.927, 30.760),
    "Калита": (50.751, 31.025),
}


# Радіус повідомлень NEPTUN
THREAT_RADIUS_KM = 25


# =================
