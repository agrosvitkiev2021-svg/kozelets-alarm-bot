import os
import re
import json
import hashlib
import math

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
import feedparser


# ============================================================
# КОНФІГУРАЦІЯ
# ============================================================

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
).strip()

CHANNEL = os.getenv(
    "CHANNEL",
    "@Kozelets_Alarm"
).strip()

UKRAINE_ALARM_API_KEY = os.getenv(
    "UKRAINE_ALARM_API_KEY",
    ""
).strip()


# ============================================================
# API
# ============================================================

UA_API = (
    "https://api.ukrainealarm.com/api/v3"
)

NEPTUN_API = (
    "https://neptun.in.ua/api/v1"
)

TELEGRAM_API = (
    f"https://api.telegram.org/bot{BOT_TOKEN}"
)


# ============================================================
# ЗАГАЛЬНІ НАЛАШТУВАННЯ
# ============================================================

TIMEOUT = 25

STATE_FILE = Path(
    "bot_state.json"
)

KYIV_TZ = ZoneInfo(
    "Europe/Kyiv"
)


# ============================================================
# ЧЕРНІГІВСЬКА ОБЛАСТЬ
# ============================================================

CHERNIHIV_REGION_ID = "25"


# ============================================================
# КООРДИНАТИ
# ============================================================

# Козелець
KOZELETS_LAT = 50.913
KOZELETS_LON = 31.121

# Остер
OSTER_LAT = 50.949
OSTER_LON = 30.886

# Радіус
THREAT_RADIUS_KM = 50


# ============================================================
# НОВИНИ
# ============================================================

# Публікуємо тільки новини,
# яким не більше 5 хвилин.

NEWS_MAX_AGE_MINUTES = 5

# Допуск для неправильної дати RSS
NEWS_FUTURE_TOLERANCE_MINUTES = 2


# ============================================================
# ЛОГ
# ============================================================

def log(text):

    print(
        text,
        flush=True
    )


# ============================================================
# DEFAULT STATE
# ============================================================

DEFAULT_STATE = {

    "alert": {

        "active": False,

        "last_change": None,

        "last_type": None
    },

    "news_seen": [],

    "history_index": 0,

    "history_last": None,

    "pinned_message_id": None,

    "threats_seen": []
}


# ============================================================
# LOAD STATE
# ============================================================

def load_state():

    if not STATE_FILE.exists():

        return json.loads(
            json.dumps(
                DEFAULT_STATE
            )
        )

    try:

        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        state = json.loads(
            json.dumps(
                DEFAULT_STATE
            )
        )

        if isinstance(
            data,
            dict
        ):

            for key in state:

                if key in data:

                    state[key] = data[key]

        return state

    except Exception as e:

        log(
            "⚠️ Помилка читання "
            f"bot_state.json: {e}"
        )

        return json.loads(
            json.dumps(
                DEFAULT_STATE
            )
        )


# ============================================================
# SAVE STATE
# ============================================================

def save_state(state):

    try:

        temp = STATE_FILE.with_suffix(
            ".tmp"
        )

        temp.write_text(
            json.dumps(
                state,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        temp.replace(
            STATE_FILE
        )

    except Exception as e:

        log(
            "⚠️ Помилка збереження "
            f"state: {e}"
        )


# ============================================================
# TELEGRAM API
# ============================================================

def telegram(
    method,
    payload=None
):

    if not BOT_TOKEN:

        log(
            "❌ BOT_TOKEN не заданий."
        )

        return None

    try:

        response = requests.post(
            f"{TELEGRAM_API}/{method}",
            json=payload or {},
            timeout=TIMEOUT
        )

        if not response.ok:

            log(
                f"❌ Telegram HTTP "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )

            return None

        data = response.json()

        if not data.get("ok"):

            log(
                f"❌ Telegram API error: "
                f"{data}"
            )

            return None

        return data.get(
            "result"
        )

    except Exception as e:

        log(
            f"❌ Telegram error: {e}"
        )

        return None


# ============================================================
# SEND MESSAGE
# ============================================================

def send_message(text):

    if len(text) > 4090:

        text = (
            text[:4080]
            + "\n…"
        )

    return telegram(
        "sendMessage",
        {
            "chat_id": CHANNEL,
            "text": text,
            "disable_web_page_preview": True
        }
    )


# ============================================================
# EDIT MESSAGE
# ============================================================

def edit_message(
    message_id,
    text
):

    if len(text) > 4090:

        text = (
            text[:4080]
            + "\n…"
        )

    return telegram(
        "editMessageText",
        {
            "chat_id": CHANNEL,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True
        }
    )


# ============================================================
# PIN MESSAGE
# ============================================================

def pin_message(
    message_id
):

    return telegram(
        "pinChatMessage",
        {
            "chat_id": CHANNEL,
            "message_id": message_id,
            "disable_notification": True
        }
    )


# ============================================================
# UKRAINE ALARM
# ============================================================

def alarm_headers():

    return {

        "Authorization":
            UKRAINE_ALARM_API_KEY,

        "Accept":
            "application/json",

        "Content-Type":
            "application/json",

        "User-Agent":
            "KozeletsAlarmBot/1.0"
    }


def get_chernihiv_alert():

    if not UKRAINE_ALARM_API_KEY:

        log(
            "⚠️ UKRAINE_ALARM_API_KEY "
            "не заданий."
        )

        return None

    url = (
        f"{UA_API}/alerts/"
        f"{CHERNIHIV_REGION_ID}"
    )

    try:

        response = requests.get(
            url,
            headers=alarm_headers(),
            timeout=TIMEOUT
        )

        if response.status_code == 401:

            log(
                "❌ UkraineAlarm: "
                "API KEY недійсний."
            )

            return None

        if response.status_code == 403:

            log(
                "❌ UkraineAlarm: "
                "доступ заборонений."
            )

            return None

        if response.status_code == 404:

            log(
                "❌ UkraineAlarm: "
                "Чернігівську область "
                "не знайдено."
            )

            return None

        if not response.ok:

            log(
                f"❌ UkraineAlarm HTTP "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )

            return None

        data = response.json()

        log(
            "✅ UkraineAlarm: "
            "отримано статус "
            "Чернігівської області."
        )

        return data

    except requests.RequestException as e:

        log(
            f"❌ UkraineAlarm network error: "
            f"{e}"
        )

        return None

    except Exception as e:

        log(
            f"❌ UkraineAlarm error: "
            f"{e}"
        )

        return None


def extract_active_alerts(
    data
):

    if data is None:
        return []

    if isinstance(
        data,
        list
    ):
        return data

    if not isinstance(
        data,
        dict
    ):
        return []

    active = data.get(
        "activeAlerts"
    )

    if isinstance(
        active,
        list
    ):

        return active

    for key in (
        "alerts",
        "active_alerts",
        "items",
        "data"
    ):

        value = data.get(
            key
        )

        if isinstance(
            value,
            list
        ):

            return value

    return []


def alert_is_active(
    data
):

    if data is None:
        return False

    active_alerts = (
        extract_active_alerts(
            data
        )
    )

    if len(active_alerts) > 0:
        return True

    if isinstance(
        data,
        dict
    ):

        for key in (
            "active",
            "isActive",
            "is_active",
            "alert"
        ):

            value = data.get(
                key
            )

            if isinstance(
                value,
                bool
            ):

                if value:
                    return True

            if str(
                value
            ).lower() in (
                "true",
                "1",
                "active"
            ):

                return True

    return False


def get_alert_type(
    data
):

    alerts = (
        extract_active_alerts(
            data
        )
    )

    if not alerts:

        return (
            "Повітряна тривога"
        )

    first = alerts[0]

    if isinstance(
        first,
        dict
    ):

        for key in (
            "type",
            "alertType",
            "alarmType",
            "name"
        ):

            value = first.get(
                key
            )

            if value:

                return str(
                    value
                )

    return (
        "Повітряна тривога"
    )


# ============================================================
# ОБРОБКА ПОВІТРЯНОЇ ТРИВОГИ
# ============================================================

def process_alarm(
    state
):

    log(
        "🚨 Перевіряю "
        "повітряну тривогу..."
    )

    if not UKRAINE_ALARM_API_KEY:

        log(
            "⚠️ UKRAINE_ALARM_API_KEY "
            "не заданий."
        )

        return

    data = get_chernihiv_alert()

    if data is None:

        log(
            "⚠️ Стан Чернігівської "
            "області не отримано."
        )

        return

    active = alert_is_active(
        data
    )

    old_active = bool(
        state["alert"].get(
            "active",
            False
        )
    )

    alert_type = get_alert_type(
        data
    )

    now = datetime.now(
        KYIV_TZ
    ).strftime(
        "%d.%m.%Y %H:%M:%S"
    )

    if active:

        log(
            "🚨 Стан Чернігівської "
            "області: 🔴 ТРИВОГА"
        )

    else:

        log(
            "🚨 Стан Чернігівської "
            "області: 🟢 НЕМАЄ ТРИВОГИ"
        )

    # --------------------------------------------------------
    # ПОЧАТОК
    # --------------------------------------------------------

    if active and not old_active:

        message = (

            "🚨 ПОВІТРЯНА ТРИВОГА\n\n"

            "📍 Чернігівська область\n"

            f"⚠️ Тип: {alert_type}\n\n"

            "Негайно прямуйте до укриття "
            "та стежте за офіційними "
            "повідомленнями."
        )

        result = send_message(
            message
        )

        if result:

            state["alert"]["active"] = True

            state["alert"]["last_change"] = now

            state["alert"]["last_type"] = (
                alert_type
            )

            save_state(
                state
            )

            log(
                "🚨 Повідомлення про "
                "початок тривоги НАДІСЛАНО."
            )

    # --------------------------------------------------------
    # ВІДБІЙ
    # --------------------------------------------------------

    elif not active and old_active:

        message = (

            "🟢 ВІДБІЙ "
            "ПОВІТРЯНОЇ ТРИВОГИ\n\n"

            "📍 Чернігівська область\n\n"

            "Офіційно отримано відбій "
            "повітряної тривоги."
        )

        result = send_message(
            message
        )

        if result:

            state["alert"]["active"] = False

            state["alert"]["last_change"] = now

            state["alert"]["last_type"] = (
                "end"
            )

            save_state(
                state
            )

            log(
                "🟢 Повідомлення про "
                "відбій НАДІСЛАНО."
            )

    # --------------------------------------------------------
    # БЕЗ ЗМІНИ
    # --------------------------------------------------------

    else:

        state["alert"]["active"] = active

        save_state(
            state
        )

        if active:

            log(
                "ℹ️ Тривога продовжується."
            )

        else:

            log(
                "ℹ️ Тривоги немає."
            )


# ============================================================
# ВІДСТАНЬ МІЖ ДВОМА ТОЧКАМИ
# ============================================================

def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius = 6371.0

    lat1_rad = math.radians(
        lat1
    )

    lat2_rad = math.radians(
        lat2
    )

    delta_lat = math.radians(
        lat2 - lat1
    )

    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(
            delta_lat / 2
        ) ** 2

        +

        math.cos(
            lat1_rad
        )

        *

        math.cos(
            lat2_rad
        )

        *

        math.sin(
            delta_lon / 2
        ) ** 2
    )

    c = (
        2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )

    return earth_radius * c


# ============================================================
# НАЗВА ТИПУ ЗАГРОЗИ
# ============================================================

def threat_type_name(
    threat
):

    threat_type = str(
        threat.get(
            "type",
            "unknown"
        )
    ).lower()

    title = str(
        threat.get(
            "title",
            ""
        )
    ).strip()

    if (
        "shahed" in title.lower()
        or "шахед" in title.lower()
    ):

        return "ШАХЕД / БпЛА"

    if threat_type == "uav":

        return "БпЛА"

    if threat_type == "missile":

        return "РАКЕТА"

    if threat_type == "ballistic":

        return "БАЛІСТИЧНА РАКЕТА"

    if threat_type == "kab":

        return "КАБ"

    if threat_type == "recon":

        return "РОЗВІДУВАЛЬНИЙ БпЛА"

    if threat_type == "mig31k":

        return "МіГ-31К"

    return (
        title
        if title
        else "ПОВІТРЯНА ЗАГРОЗА"
    )


# ============================================================
# ПЕРЕВІРКА — ЦІКАВИТЬ ЛИШЕ БПЛА/РАКЕТИ
# ============================================================

def is_relevant_threat(
    threat
):

    threat_type = str(
        threat.get(
            "type",
            ""
        )
    ).lower()

    # Шахеди / БпЛА
    if threat_type == "uav":
        return True

    # Крилаті ракети
    if threat_type == "missile":
        return True

    # Балістика
    if threat_type == "ballistic":
        return True

    return False


# ============================================================
# ПЕРЕВІРКА ЗАГРОЗ NEPTUN
# ============================================================

def check_neptun_threats(
    state
):

    log(
        "🛰 Перевіряю "
        "повітряні загрози NEPTUN..."
    )

    url = (
        f"{NEPTUN_API}/threats"
    )

    try:

        response = requests.get(
            url,
            timeout=TIMEOUT,
            headers={
                "Accept":
                    "application/json",
                "User-Agent":
                    "KozeletsAlarmBot/1.0"
            }
        )

        if not response.ok:

            log(
                "⚠️ NEPTUN HTTP "
                f"{response.status_code}: "
                f"{response.text[:300]}"
            )

            return

        data = response.json()

        threats = data.get(
            "threats",
            []
        )

        if not isinstance(
            threats,
            list
        ):

            log(
                "⚠️ NEPTUN: "
                "некоректний формат threats."
            )

            return

        log(
            f"🛰 NEPTUN: "
            f"активних об'єктів: "
            f"{len(threats)}"
        )

        seen_threats = set(
            state.get(
                "threats_seen",
                []
            )
        )

        relevant_ids = set()

        for threat in threats:

            if not isinstance(
                threat,
                dict
            ):

                continue

            # ------------------------------------------------
            # ТІЛЬКИ БПЛА / РАКЕТИ
            # ------------------------------------------------

            if not is_relevant_threat(
                threat
            ):

                continue

            # ------------------------------------------------
            # ТІЛЬКИ ACTIVE
            # ------------------------------------------------

            status = str(
                threat.get(
                    "status",
                    ""
                )
            ).lower()

            if status != "active":

                continue

            # ------------------------------------------------
            # AREA ONLY
            # ------------------------------------------------
            #
            # Якщо NEPTUN каже, що координата
            # є лише центроїдом області,
            # не використовуємо її як точку
            # реальної загрози.
            # ------------------------------------------------

            if threat.get(
                "areaOnly",
                False
            ):

                log(
                    "⏭️ NEPTUN: "
                    "areaOnly — пропускаю."
                )

                continue

            # ------------------------------------------------
            # КООРДИНАТИ
            # ------------------------------------------------

            lat = threat.get(
                "lat"
            )

            lon = threat.get(
                "lon"
            )

            if lat is None or lon is None:

                continue

            try:

                lat = float(lat)

                lon = float(lon)

            except (
                TypeError,
                ValueError
            ):

                continue

            # ------------------------------------------------
            # ДАНІ ПРО ОБ'ЄКТ
            # ------------------------------------------------

            threat_id = str(
                threat.get(
                    "id",
                    ""
                )
            ).strip()

            if not threat_id:

                # Запасний ID
                raw = (
                    f"{threat.get('type')}|"
                    f"{lat}|"
                    f"{lon}|"
                    f"{threat.get('updatedAt')}"
                )

                threat_id = hashlib.sha256(
                    raw.encode("utf-8")
                ).hexdigest()[:24]

            relevant_ids.add(
                threat_id
            )

            # ------------------------------------------------
            # ВІДСТАНЬ ДО КОЗЕЛЬЦЯ
            # ------------------------------------------------

            kozelets_distance = (
                distance_km(
                    lat,
                    lon,
                    KOZELETS_LAT,
                    KOZELETS_LON
                )
            )

            # ------------------------------------------------
            # ВІДСТАНЬ ДО ОСТРА
            # ------------------------------------------------

            oster_distance = (
                distance_km(
                    lat,
                    lon,
                    OSTER_LAT,
                    OSTER_LON
                )
            )

            # ------------------------------------------------
            # ВИБИРАЄМО НАЙБЛИЖЧЕ МІСЦЕ
            # ------------------------------------------------

            if (
                kozelets_distance
                <= THREAT_RADIUS_KM
                and
                (
                    kozelets_distance
                    <= oster_distance
                )
            ):

                nearest_place = (
                    "Козельця"
                )

                nearest_distance = (
                    kozelets_distance
                )

            elif (
                oster_distance
                <= THREAT_RADIUS_KM
            ):

                nearest_place = (
                    "Остра"
                )

                nearest_distance = (
                    oster_distance
                )

            else:

                continue

            # ------------------------------------------------
            # ВЖЕ ПОВІДОМЛЯЛИ
            # ------------------------------------------------

            if threat_id in seen_threats:

                log(
                    "ℹ️ NEPTUN: "
                    f"об'єкт {threat_id} "
                    "вже повідомлявся."
                )

                continue

            # ------------------------------------------------
            # ТИП
            # ------------------------------------------------

            type_name = (
                threat_type_name(
                    threat
                )
            )

            # ------------------------------------------------
            # НАЗВА
            # ------------------------------------------------

            title = str(
                threat.get(
                    "title",
                    ""
                )
            ).strip()

            # ------------------------------------------------
            # НАПРЯМОК
            # ------------------------------------------------

            heading = threat.get(
                "heading"
            )

            direction_text = ""

            if heading is not None:

                try:

                    heading_value = (
                        float(heading)
                    )

                    direction_text = (
                        f"\n🧭 Курс: "
                        f"{heading_value:.0f}°"
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    pass

            # ------------------------------------------------
            # РАЙОН / ОБЛАСТЬ
            # ------------------------------------------------

            location_parts = []

            region = str(
                threat.get(
                    "region",
                    ""
                )
            ).strip()

            district = str(
                threat.get(
                    "district",
                    ""
                )
            ).strip()

            locality = str(
                threat.get(
                    "locality",
                    ""
                )
            ).strip()

            if locality:

                location_parts.append(
                    locality
                )

            elif district:

                location_parts.append(
                    district
                )

            elif region:

                location_parts.append(
                    region
                )

            location_text = ""

            if location_parts:

                location_text = (
                    "\n📍 Район: "
                    + ", ".join(
                        location_parts
                    )
                )

            # ------------------------------------------------
            # ГРУПА
            # ------------------------------------------------

            count = threat.get(
                "count"
            )

            count_text = ""

            if count:

                try:

                    count_value = int(
                        count
                    )

                    if count_value > 1:

                        count_text = (
                            f"\n🔢 Група: "
                            f"{count_value} об'єктів"
                        )

                except (
                    TypeError,
                    ValueError
                ):

                    pass

            # ------------------------------------------------
            # CONFIDENCE
            # ------------------------------------------------

            confidence = str(
                threat.get(
                    "confidenceLevel",
                    ""
                )
            ).lower()

            confidence_text = ""

            if confidence == "high":

                confidence_text = (
                    "\n📊 Достовірність: "
                    "висока"
                )

            elif confidence == "medium":

                confidence_text = (
                    "\n📊 Достовірність: "
                    "середня"
                )

            elif confidence == "low":

                confidence_text = (
                    "\n📊 Достовірність: "
                    "низька"
                )

            # ------------------------------------------------
            # ЧАС
            # ------------------------------------------------

            updated_at = str(
                threat.get(
                    "updatedAt",
                    ""
                )
            ).strip()

            time_text = ""

            if updated_at:

                try:

                    dt = datetime.fromisoformat(
                        updated_at.replace(
                            "Z",
                            "+00:00"
                        )
                    )

                    dt = dt.astimezone(
                        KYIV_TZ
                    )

                    time_text = (
                        "\n🕐 Оновлено: "
                        + dt.strftime(
                            "%d.%m.%Y %H:%M:%S"
                        )
                    )

                except Exception:

                    pass

            # ------------------------------------------------
            # ФОРМУЄМО ПОВІДОМЛЕННЯ
            # ------------------------------------------------

            if (
                threat.get(
                    "advisory",
                    False
                )
            ):

                prefix = (
                    "ℹ️ ІНФОРМАЦІЯ "
                    "ПРО ПОВІТРЯНУ ЗАГРОЗУ"
                )

            else:

                prefix = (
                    "🚨 ПОВІТРЯНА ЗАГРОЗА "
                    "ПОБЛИЗУ"
                )

            message = (

                f"{prefix}\n\n"

                f"📍 Поблизу {nearest_place}\n"

                f"⚠️ Тип: {type_name}\n"

                f"📏 Відстань: "
                f"≈ {nearest_distance:.0f} км"

                f"{direction_text}"

                f"{location_text}"

                f"{count_text}"

                f"{confidence_text}"

                f"{time_text}"

                "\n\n"

                "⚠️ Це інформаційні дані "
                "NEPTUN, а не офіційний "
                "сигнал повітряної тривоги."

                "\n\n"

                "🔗 Дані: "
                "https://neptun.in.ua/"
            )

            result = send_message(
                message
            )

            if result:

                seen_threats.add(
                    threat_id
                )

                log(
                    "🚨 NEPTUN: "
                    f"повідомлення надіслано — "
                    f"{type_name}, "
                    f"≈{nearest_distance:.0f} км "
                    f"від {nearest_place}"
                )

        # ----------------------------------------------------
        # ОЧИЩЕННЯ СТАРИХ ID
        # ----------------------------------------------------
        #
        # Зберігаємо тільки актуальні об'єкти
        # плюс невелику історію.
        # ----------------------------------------------------

        current_seen = (
            seen_threats
            & relevant_ids
        )

        # Зберігаємо максимум 500 ID.
        #
        # Якщо загроза зникла з активних —
        # її ID очищається.
        #
        state["threats_seen"] = list(
            current_seen
        )[-500:]

        save_state(
            state
        )

        log(
            "🛰 Перевірка NEPTUN завершена."
        )

    except requests.RequestException as e:

        log(
            f"⚠️ NEPTUN network error: "
            f"{e}"
        )

    except Exception as e:

        log(
            f"⚠️ NEPTUN error: "
            f"{e}"
        )


# ============================================================
# WEATHER
# ============================================================

def get_weather():

    url = (

        "https://api.open-meteo.com/v1/forecast"

        f"?latitude={KOZELETS_LAT}"

        f"&longitude={KOZELETS_LON}"

        "&current="
        "temperature_2m,"
        "relative_humidity_2m,"
        "apparent_temperature,"
        "precipitation,"
        "rain,"
        "weather_code,"
        "wind_speed_10m,"
        "wind_direction_10m"

        "&timezone=Europe%2FKyiv"

        "&forecast_days=1"
    )

    try:

        response = requests.get(
            url,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:

        log(
            f"⚠️ Weather error: "
            f"{e}"
        )

        return None


def weather_description(
    code
):

    descriptions = {

        0: "ясно",

        1: "переважно ясно",

        2: "мінлива хмарність",

        3: "хмарно",

        45: "туман",

        48: "туман",

        51: "слабка мряка",

        53: "мряка",

        55: "сильна мряка",

        61: "слабкий дощ",

        63: "дощ",

        65: "сильний дощ",

        71: "слабкий сніг",

        73: "сніг",

        75: "сильний сніг",

        80: "зливи",

        81: "зливи",

        82: "сильні зливи",

        95: "гроза",

        96: "гроза з градом",

        99: "гроза з градом"
    }

    return descriptions.get(
        code,
        "невідомо"
    )


# ============================================================
# NEWS FEEDS
# ============================================================

NEWS_FEEDS = [

    (
        "Козелець",

        "https://news.google.com/rss/search?q="
        + quote(
            "Козелець Україна"
        )
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),

    (
        "Остер",

        "https://news.google.com/rss/search?q="
        + quote(
            "Остер Чернігівська область"
        )
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),

    (
        "Бобровиця",

        "https://news.google.com/rss/search?q="
        + quote(
            "Бобровиця Чернігівська область"
        )
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),

    (
        "Козелеччина",

        "https://news.google.com/rss/search?q="
        + quote(
            "Козелеччина"
        )
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),

    (
        "ДСНС Чернігів",

        "https://news.google.com/rss/search?q="
        + quote(
            "ДСНС Чернігівська область"
        )
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),

    (
        "Поліція Чернігів",

        "https://news.google.com/rss/search?q="
        + quote(
            "поліція Чернігівська область"
        )
        + "&hl=uk&gl=UA&ceid=UA:uk"
    )
]


# ============================================================
# CLEAN NEWS
# ============================================================

def clean_text(
    text
):

    text = text or ""

    text = re.sub(
        r"<[^>]+>",
        "",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# NEWS ID
# ============================================================

def make_news_id(
    title,
    link
):

    value = (
        f"{title}|{link}"
    )

    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()[:24]


# ============================================================
# PARSE NEWS DATE
# ============================================================

def parse_news_date(
    entry
):

    parsed = None

    if entry.get(
        "published_parsed"
    ):

        parsed = entry.get(
            "published_parsed"
        )

    elif entry.get(
        "updated_parsed"
    ):

        parsed = entry.get(
            "updated_parsed"
        )

    if not parsed:

        return None

    try:

        return datetime(
            parsed.tm_year,
            parsed.tm_mon,
            parsed.tm_mday,
            parsed.tm_hour,
            parsed.tm_min,
            parsed.tm_sec,
            tzinfo=timezone.utc
        )

    except Exception:

        return None


# ============================================================
# NEWS
# ============================================================

def get_news(
    state
):

    log(
        "📰 Перевіряю "
        "ТІЛЬКИ свіжі новини..."
    )

    seen = set(
        state.get(
            "news_seen",
            []
        )
    )

    collected = []

    now_utc = datetime.now(
        timezone.utc
    )

    cutoff = (
        now_utc
        - timedelta(
            minutes=NEWS_MAX_AGE_MINUTES
        )
    )

    for category, url in NEWS_FEEDS:

        try:

            feed = feedparser.parse(
                url
            )

            for entry in feed.entries[:20]:

                title = clean_text(
                    entry.get(
                        "title",
                        ""
                    )
                )

                link = entry.get(
                    "link",
                    ""
                )

                if not title or not link:

                    continue

                published_dt = (
                    parse_news_date(
                        entry
                    )
                )

                if published_dt is None:

                    log(
                        "⏭️ Пропущено — "
                        f"немає дати: "
                        f"{title}"
                    )

                    continue

                if published_dt > (
                    now_utc
                    + timedelta(
                        minutes=
                        NEWS_FUTURE_TOLERANCE_MINUTES
                    )
                ):

                    log(
                        "⏭️ Пропущено — "
                        f"майбутня дата: "
                        f"{title}"
                    )

                    continue

                if published_dt < cutoff:

                    age = (
                        now_utc
                        - published_dt
                    )

                    age_minutes = (
                        age.total_seconds()
                        / 60
                    )

                    log(
                        "⏭️ Стара новина "
                        f"({age_minutes:.1f} хв): "
                        f"{title}"
                    )

                    continue

                news_id = make_news_id(
                    title,
                    link
                )

                if news_id in seen:

                    log(
                        "⏭️ Вже публікували: "
                        f"{title}"
                    )

                    continue

                collected.append(
                    (
                        category,
                        title,
                        link,
                        news_id,
                        published_dt
                    )
                )

        except Exception as e:

            log(
                f"⚠️ News error "
                f"{category}: {e}"
            )

    # Найновіші першими
    collected.sort(
        key=lambda item: item[4],
        reverse=True
    )

    # Максимум 5
    collected = collected[:5]

    published = 0

    for (
        category,
        title,
        link,
        news_id,
        published_dt
    ) in collected:

        kyiv_time = (
            published_dt
            .astimezone(
                KYIV_TZ
            )
        )

        message = (

            f"📰 {category}\n\n"

            f"🔹 {title}\n\n"

            f"🕐 "
            f"{kyiv_time.strftime('%d.%m.%Y %H:%M')}\n\n"

            f"🔗 {link}"
        )

        result = send_message(
            message
        )

        if result:

            seen.add(
                news_id
            )

            published += 1

            log(
                "📰 Опубліковано: "
                f"{title}"
            )

    state["news_seen"] = list(
        seen
    )[-500:]

    save_state(
        state
    )

    log(
        f"📰 Опубліковано новин: "
        f"{published}"
    )


# ============================================================
# HISTORY
# ============================================================

HISTORY = [

    (
        "📚 КОЗЕЛЕЦЬ",

        "Козелець — історичне містечко "
        "Чернігівщини, відоме "
        "архітектурною спадщиною "
        "та пам'ятками козацької доби."
    ),

    (
        "📚 ОСТЕР",

        "Остер — одне з давніх міст "
        "Чернігівщини, розташоване "
        "на річці Остер."
    ),

    (
        "📚 БОБРОВИЦЯ",

        "Бобровиця — місто "
        "Чернігівської області "
        "з давньою історією "
        "та залізничним сполученням."
    ),

    (
        "📚 КОЗЕЛЕЧЧИНА",

        "Козелеччина поєднує історичні "
        "населені пункти, природні "
        "території та культурну "
        "спадщину Чернігівщини."
    )
]


def history_post(
    state
):

    last = state.get(
        "history_last"
    )

    now = datetime.now(
        KYIV_TZ
    )

    if last:

        try:

            last_dt = datetime.strptime(
                last,
                "%Y-%m-%d %H:%M:%S"
            ).replace(
                tzinfo=KYIV_TZ
            )

            if (
                now - last_dt
                < timedelta(hours=12)
            ):

                return

        except Exception:

            pass

    index = int(
        state.get(
            "history_index",
            0
        )
    )

    title, text = HISTORY[
        index % len(HISTORY)
    ]

    message = (
        f"{title}\n\n"
        f"{text}\n\n"
        "📍 Чернігівщина"
    )

    result = send_message(
        message
    )

    if result:

        state["history_index"] = (
            index + 1
        )

        state["history_last"] = (
            now.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        save_state(
            state
        )

        log(
            "📚 Історичний пост "
            "опубліковано."
        )


# ============================================================
# RADIATION
# ============================================================

def radiation_info():

    return (

        "☢️ РАДІАЦІЙНИЙ ФОН\n\n"

        "ℹ️ Для коректного локального "
        "значення необхідні офіційні "
        "вимірювання.\n"

        "Джерело:\n"

        "https://www.cgmch.pp.ua/"
    )


# ============================================================
# POWER
# ============================================================

def power_info():

    return (

        "⚡ ЕЛЕКТРОПОСТАЧАННЯ\n\n"

        "ℹ️ Графік та аварійні "
        "відключення перевіряйте "
        "на офіційному ресурсі "
        "Чернігівобленерго.\n\n"

        "https://chernihivoblenergo.com.ua/blackouts"
    )


# ============================================================
# DASHBOARD
# ============================================================

def dashboard_text(
    state
):

    weather = get_weather()

    now = datetime.now(
        KYIV_TZ
    ).strftime(
        "%d.%m.%Y %H:%M"
    )

    active = bool(
        state["alert"].get(
            "active",
            False
        )
    )

    lines = [

        "📍 КОЗЕЛЕЦЬ | "
        "ОПЕРАТИВНА ПАНЕЛЬ",

        "",

        f"🕐 Оновлено: {now}",

        ""
    ]

    if active:

        lines.append(
            "🚨 ТРИВОГА: 🔴 АКТИВНА"
        )

    else:

        lines.append(
            "🚨 ТРИВОГА: 🟢 НЕ АКТИВНА"
        )

    lines.append("")

    lines.append(
        "🛰 ПОВІТРЯНІ ЗАГРОЗИ"
    )

    lines.extend([

        "📍 Козелець / Остер",

        "📏 Радіус: 50 км",

        "🚁 БпЛА / Шахеди",

        "🚀 Ракети / балістика",

        ""
    ])

    lines.append(
        "🌤 ПОГОДА"
    )

    if weather:

        try:

            current = weather[
                "current"
            ]

            temperature = current.get(
                "temperature_2m"
            )

            feels = current.get(
                "apparent_temperature"
            )

            humidity = current.get(
                "relative_humidity_2m"
            )

            wind = current.get(
                "wind_speed_10m"
            )

            code = current.get(
                "weather_code"
            )

            lines.extend([

                f"🌡 Температура: "
                f"{temperature} °C",

                f"🌡 Відчувається: "
                f"{feels} °C",

                f"💧 Вологість: "
                f"{humidity}%",

                f"💨 Вітер: "
                f"{wind} км/год",

                f"☁️ Стан: "
                f"{weather_description(code)}",

                ""
            ])

        except Exception:

            lines.extend([

                "⚠️ Дані погоди "
                "тимчасово недоступні.",

                ""
            ])

    else:

        lines.extend([

            "⚠️ Дані погоди "
            "тимчасово недоступні.",

            ""
        ])

    lines.append(
        radiation_info()
    )

    lines.append("")

    lines.append(
        power_info()
    )

    lines.extend([

        "",

        "📰 Новини: "
        "тільки за останні 5 хвилин",

        "",

        "🔄 Автоматичне оновлення: "
        "кожні 5 хвилин"
    ])

    return "\n".join(
        lines
    )


# ============================================================
# UPDATE DASHBOARD
# ============================================================

def update_dashboard(
    state
):

    text = dashboard_text(
        state
    )

    message_id = state.get(
        "pinned_message_id"
    )

    if message_id:

        result = edit_message(
            message_id,
            text
        )

        if result:

            log(
                "📌 Панель оновлено."
            )

            return

        log(
            "⚠️ Стару панель "
            "не вдалося оновити."
        )

    result = send_message(
        text
    )

    if not result:

        log(
            "❌ Не вдалося створити "
            "панель."
        )

        return

    new_id = result.get(
        "message_id"
    )

    if not new_id:

        return

    state[
        "pinned_message_id"
    ] = new_id

    save_state(
        state
    )

    pin_message(
        new_id
    )

    log(
        "📌 Панель створена "
        "та закріплена."
    )


# ============================================================
# CONFIG VALIDATION
# ============================================================

def validate_config():

    valid = True

    if not BOT_TOKEN:

        log(
            "❌ BOT_TOKEN не заданий."
        )

        valid = False

    if not CHANNEL:

        log(
            "❌ CHANNEL не заданий."
        )

        valid = False

    if not UKRAINE_ALARM_API_KEY:

        log(
            "❌ UKRAINE_ALARM_API_KEY "
            "не заданий."
        )

        valid = False

    return valid


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "=" * 60
    )

    print(
        "🤖 KOZELETS ALARM BOT"
    )

    print(
        "=" * 60
    )

    print(
        datetime.now(
            KYIV_TZ
        ).strftime(
            "%d.%m.%Y %H:%M:%S"
        )
    )

    print(
        "=" * 60
    )

    if not validate_config():

        log(
            "❌ Конфігурація неповна."
        )

        return

    state = load_state()

    # --------------------------------------------------------
    # 1. ОФІЦІЙНА ТРИВОГА
    # --------------------------------------------------------

    process_alarm(
        state
    )

    # --------------------------------------------------------
    # 2. NEPTUN
    # --------------------------------------------------------

    check_neptun_threats(
        state
    )

    # --------------------------------------------------------
    # 3. DASHBOARD
    # --------------------------------------------------------

    update_dashboard(
        state
    )

    # --------------------------------------------------------
    # 4. NEWS
    # --------------------------------------------------------

    get_news(
        state
    )

    # --------------------------------------------------------
    # 5. HISTORY
    # --------------------------------------------------------

    history_post(
        state
    )

    # --------------------------------------------------------
    # 6. SAVE
    # --------------------------------------------------------

    save_state(
        state
    )

    print(
        "=" * 60
    )

    print(
        "✅ ЦИКЛ ЗАВЕРШЕНО"
    )

    print(
        "=" * 60
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
