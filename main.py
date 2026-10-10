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


# ============================================================
# НОВИНИ
# ============================================================

NEWS_FEEDS = [
    (
        "Козелець",
        "https://news.google.com/rss/search?"
        "q=%D0%9A%D0%BE%D0%B7%D0%B5%D0%BB%D0%B5%D1%86%D1%8C"
        "&hl=uk&gl=UA&ceid=UA:uk"
    ),
    (
        "Остер",
        "https://news.google.com/rss/search?"
        "q=%D0%9E%D1%81%D1%82%D0%B5%D1%80+%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%Bа"
        "&hl=uk&gl=UA&ceid=UA:uk"
    ),
    (
        "Чернігівська область",
        "https://news.google.com/rss/search?"
        "q=%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%Bа+%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C"
        "&hl=uk&gl=UA&ceid=UA:uk"
    ),
]


# ============================================================
# ІСТОРІЯ ТА ВИДАТНІ МІСЦЯ КОЗЕЛЕЧЧИНИ
# ============================================================

LOCAL_HISTORY_POSTS = [
    (
        "🏛 <b>Історія Козельця: Собор Різдва Богородиці</b>\n\n"
        "Величний архітектурний шедевр у стилі українського бароко, збудований у 1752–1763 роках коштом графині Віри Разумовської (матері Олексія та Кирила Розумовських). "
        "Головна святиня храму — унікальний п'ятиярусний різьблений іконостас.\n\n"
        "📌 <i>Цікавий факт:</i> За легендою, іконостас спочатку виготовляли для іншого храму, але він вразив своєю красою, і його встановили саме в Козельці."
    ),
    (
        "📜 <b>Козацьке минуле Козельця</b>\n\n"
        "У XVII–XVIII століттях Козелець був сотенним містечком Київського полку. Тут активно розвивалося ремесло та торгівля, а міська старшина відігравала важливу роль у регіоні.\n\n"
        "📌 <i>Цікавий факт:</i> У 1656 році Богдан Хмельницький надав Козельцю Магдебурзьке право, що дало місту самоврядування та власний герб."
    ),
    (
        "🏛 <b>Поштова станція у Козельці</b>\n\n"
        "Комплекс споруд колишньої поштової станції (середина XIX століття) — одна з небагатьох добре збережених пам'яток дорожньої архітектури в Україні.\n\n"
        "📌 <i>Цікавий факт:</i> Тут свого часу зупинялися видатні діячі культури, зокрема Тарас Шевченко, який подорожував Лівобережною Україною та замальовував місцеві краєвиди."
    ),
    (
        "🌿 <b>Остерський міст та руїни «Божниці»</b>\n\n"
        "Неподалік від Козельця, у місті Остер, знаходяться залишки давньоруського Михайлівського храму (XII ст.), відомого як «Божниця» — єдиної вцілілої споруди стародавнього Остра часів Київської Русі.\n\n"
        "📌 <i>Цікавий факт:</i> Храм збудував ще князь Володимир Мономах як частину укріпленого дитинця."
    ),
    (
        "⭐ <b>Видатні постаті: родина Розумовських</b>\n\n"
        "Козелеччина тісно пов'язана з родом Розумовських, які залишили величезний слід в історії української та європейської культури.\n\n"
        "📌 <i>Цікавий факт:</i> Завдяки фінансовій підтримці та впливу Розумовських у Козельці та на сусідніх територіях з'явилися монументальні кам'яні храми та розвинулася освіта."
    )
]

PROMO_POSTS = [
    (
        "📢 <b>Долучайтеся до нашої спільноти!</b>\n\n"
        "Запрошуйте друзів та знайомих до нашого каналу — оперативні новини, безпека та історія Козелеччини разом.\n\n"
        "🔗 Поділіться посиланням на канал з тими, хто тут мешкає!"
    )
]


# ============================================================
# TELEGRAM API
# ============================================================

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram_send(text, show_buttons=True, comment_url=None):
    """
    Відправка повідомлення в Telegram з Inline-кнопками «Поділитися» та «Обговорити».
    """
    try:
        channel_name = CHANNEL.replace("@", "") if CHANNEL.startswith("@") else CHANNEL
        channel_link = f"https://t.me/{channel_name}"
        
        share_text = "Оперативні сповіщення, тривоги та новини Козелеччини! 🔔"
        share_url = (
            f"https://t.me/share/url?"
            f"url={requests.utils.quote(channel_link)}&"
            f"text={requests.utils.quote(share_text)}"
        )

        data = {
            "chat_id": CHANNEL,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        if show_buttons:
            row_buttons = [
                {
                    "text": "📢 Поділитися",
                    "url": share_url
                }
            ]

            discussion_link = comment_url if comment_url else channel_link
            row_buttons.append({
                "text": "💬 Обговорити",
                "url": discussion_link
            })

            reply_markup = {
                "inline_keyboard": [
                    row_buttons
                ]
            }
            data["reply_markup"] = json.dumps(reply_markup)

        response = requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            data=data,
            timeout=30,
        )

        if response.status_code == 200:
            print("✅ Telegram: повідомлення успішно опубліковано.")
            return True

        print(
            f"❌ Telegram помилка {response.status_code}: "
            f"{response.text[:500]}"
        )

    except Exception as e:
        print(f"❌ Помилка відправки в Telegram: {e}")

    return False


# ============================================================
# STATE
# ============================================================

def default_state():
    return {
        # NEPTUN
        "active_threats": {},
        "last_threat_update": 0,

        # Новини
        "last_news_check": 0,
        "published_news": [],

        # Погода
        "last_weather_check": 0,

        # Промо
        "last_promo_check": 0,

        # Історія
        "last_history_check": 0,
        "published_history_indexes": [],

        # Офіційна тривога Чернігівського району
        "district_alert_active": None,

        # Чи вже отримували хоча б один успішний стан API
        "district_alert_initialized": False,
    }


def load_state():
    if not STATE_FILE.exists():
        print("ℹ️ bot_state.json не знайдено. Створюю новий стан.")
        return default_state()

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            state = json.load(file)

        base = default_state()
        base.update(state)

        return base

    except Exception as e:
        print(
            f"⚠️ Помилка читання bot_state.json: {e}"
        )
        return default_state()


def save_state(state):
    try:
        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                state,
                file,
                ensure_ascii=False,
                indent=2
            )

        print("💾 Стан бота збережено.")

    except Exception as e:
        print(
            f"❌ Помилка збереження bot_state.json: {e}"
        )


# ============================================================
# ЧАС
# ============================================================

def now_timestamp():
    return datetime.now(
        timezone.utc
    ).timestamp()


def kyiv_time():
    return datetime.now(
        timezone.utc
    ) + timedelta(hours=3)


def current_time_string():
    return kyiv_time().strftime("%H:%M")


# ============================================================
# ГЕОЛОКАЦІЯ
# ============================================================

def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):
    try:
        radius = 6371.0

        lat1 = math.radians(float(lat1))
        lon1 = math.radians(float(lon1))

        lat2 = math.radians(float(lat2))
        lon2 = math.radians(float(lon2))

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            math.sin(dlat / 2) ** 2
            +
            math.cos(lat1)
            *
            math.cos(lat2)
            *
            math.sin(dlon / 2) ** 2
        )

        c = 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )

        return radius * c

    except Exception:
        return None


def nearest_place(
    lat,
    lon
):
    best_name = None
    best_distance = None

    for name, coords in PLACES.items():
        distance = distance_km(
            lat,
            lon,
            coords[0],
            coords[1]
        )

        if distance is None:
            continue

        if (
            best_distance is None
            or distance < best_distance
        ):
            best_name = name
            best_distance = distance

    return best_name, best_distance


# ============================================================
# ДОПОМІЖНА ФУНКЦІЯ ДЛЯ JSON
# ============================================================

def get_value(
    data,
    *keys
):
    if not isinstance(data, dict):
        return None

    for key in keys:
        value = data.get(key)

        if value is not None and value != "":
            return value

    return None


# ============================================================
# ОФІЦІЙНА ПОВІТРЯНА ТРИВОГА
# ЧЕРНІГІВСЬКИЙ РАЙОН
# ============================================================

def get_district_alert():
    print(
        f"🚨 Перевіряю офіційний API: "
        f"{AIR_REGION_NAME}..."
    )

    headers = {
        "Authorization": AIR_API_TOKEN,
        "Accept": "application/json",
        "User-Agent": "KozeletsAlarmBot/1.0",
    }

    try:
        response = requests.get(
            AIR_API_URL,
            headers=headers,
            timeout=30,
        )

        print(
            f"UkraineAlarm HTTP: "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            print(
                "❌ Помилка API UkraineAlarm:"
                f" {response.text[:500]}"
            )
            return None

        data = response.json()

        print(
            "✅ UkraineAlarm: "
            "дані Чернігівського району отримано."
        )

        return parse_district_alert(data)

    except requests.exceptions.RequestException as e:
        print(
            f"❌ Помилка з'єднання UkraineAlarm: {e}"
        )

    except Exception as e:
        print(
            f"❌ Помилка обробки UkraineAlarm: {e}"
        )

    return None


def parse_district_alert(data):
    """
    API може повертати масив регіонів.
    Обробляємо декілька можливих форматів.
    """
    item = None

    if isinstance(data, list):
        if len(data) == 0:
            return False
        item = data[0]

    elif isinstance(data, dict):
        if (
            "activeAlerts" in data
            or "regionName" in data
            or "regionId" in data
        ):
            item = data

        elif isinstance(
            data.get("states"),
            list
        ):
            for state in data["states"]:
                state_id = get_value(
                    state,
                    "regionId",
                    "id",
                    "region_id"
                )

                if str(state_id) == str(
                    AIR_REGION_ID
                ):
                    item = state
                    break

            if item is None and data["states"]:
                item = data["states"][0]

    if not isinstance(item, dict):
        print(
            "⚠️ Не вдалося знайти стан "
            "Чернігівського району."
        )
        return None

    active_alerts = item.get("activeAlerts")

    if isinstance(active_alerts, list):
        active = len(active_alerts) > 0

    elif isinstance(active_alerts, dict):
        active = len(active_alerts) > 0

    elif isinstance(active_alerts, bool):
        active = active_alerts

    else:
        active_value = get_value(
            item,
            "active",
            "isActive"
        )

        if isinstance(active_value, bool):
            active = active_value
        else:
            active = False

    print(
        f"🚨 {AIR_REGION_NAME}: "
        f"{'🔴 ТРИВОГА' if active else '🟢 ВІДБІЙ'}"
    )

    return active


def process_district_alert(state):
    current_alert = get_district_alert()

    if current_alert is None:
        print(
            "⚠️ Стан тривоги не змінюю, "
            "оскільки API не відповів."
        )
        return

    previous_alert = state.get("district_alert_active")
