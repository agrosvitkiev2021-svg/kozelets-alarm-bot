import os
import re
import json
import hashlib
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import feedparser


# ============================================================
# НАЛАШТУВАННЯ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL = os.getenv("CHANNEL", "@Kozelets_Alarm").strip()

UKRAINE_ALARM_API_KEY = os.getenv(
    "UKRAINE_ALARM_API_KEY",
    ""
).strip()

UA_API = "https://api.ukrainealarm.com/api/v3"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

NEPTUN_API = "https://neptun.in.ua/api/v1/threats"

# Короткі таймаути, щоб один сервіс не зависав надовго
TIMEOUT = 10
NEWS_TIMEOUT = 8

STATE_FILE = Path("bot_state.json")

# Чернігівська область
CHERNIHIV_REGION_ID = "25"

# Козелець
KOZELETS_LAT = 50.913
KOZELETS_LON = 31.121

# Остер
OSTER_LAT = 50.950
OSTER_LON = 30.883

# Радіус NEPTUN
THREAT_RADIUS_KM = 30

# Новини не старші 30 хвилин
NEWS_MAX_AGE_MINUTES = 30

# Основний цикл — кожну хвилину
MAIN_LOOP_SECONDS = 60

# Панель — кожні 5 хвилин
DASHBOARD_INTERVAL = 300

# Погода — максимум раз на 10 хвилин
WEATHER_INTERVAL = 600

# Промо — кожні 4 години
PROMO_INTERVAL_HOURS = 4

# Історія — раз на 12 годин
HISTORY_INTERVAL_HOURS = 12


# ============================================================
# ПРОСУВАННЯ КАНАЛУ
# ============================================================

PROMO_STATE_KEY = "promotion"

PROMO_MESSAGES = [
    (
        "📢 КОРИСНИЙ МІСЦЕВИЙ КАНАЛ\n\n"
        "🚨 Повітряні тривоги та відбої\n"
        "📰 Свіжі новини Козельця, Остра та Чернігівщини\n"
        "🌤 Погода та важлива місцева інформація\n\n"
        "Щоб нічого важливого не пропустити — підписуйтесь 👇\n"
        "👉 https://t.me/Kozelets_Alarm\n\n"
        "📲 Перешліть цей допис рідним та друзям."
    ),
    (
        "📍 КОЗЕЛЕЦЬ | ЧЕРНІГІВЩИНА\n\n"
        "Хочете першими бачити важливі місцеві повідомлення?\n\n"
        "🚨 Тривоги та відбої\n"
        "📰 Місцеві новини\n"
        "⚡ Важливі події та комунальна інформація\n\n"
        "Підписуйтесь на канал:\n"
        "👉 https://t.me/Kozelets_Alarm\n\n"
        "👥 Запросіть до каналу тих, кому це може бути корисно."
    ),
    (
        "🔔 НЕ ПРОПУСКАЙТЕ ВАЖЛИВЕ\n\n"
        "Канал «Козелець Повітряна Тривога!» автоматично стежить за важливими подіями та новинами регіону.\n\n"
        "📍 Козелець\n"
        "📍 Остер\n"
        "📍 Чернігівщина\n\n"
        "👉 Підписатися: https://t.me/Kozelets_Alarm\n\n"
        "💙 Якщо маєте друзів або родичів у нашому районі — перешліть їм цей допис."
    ),
    (
        "📣 ЗАПРОШУЄМО ПІДПИСАТИСЯ\n\n"
        "Один канал — важливі події вашого регіону:\n\n"
        "🚨 Повітряні тривоги\n"
        "🟢 Відбої\n"
        "📰 Новини\n"
        "🌤 Погода\n"
        "📍 Козелець та Чернігівщина\n\n"
        "👉 https://t.me/Kozelets_Alarm\n\n"
        "Підписуйтесь та поділіться каналом із близькими."
    ),
]


# ============================================================
# НОВИНИ
# ============================================================

NEWS_FEEDS = [
    (
        "Козелець",
        "https://news.google.com/rss/search?q="
        + quote("Козелець")
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),
    (
        "Остер",
        "https://news.google.com/rss/search?q="
        + quote("Остер Чернігівська область")
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),
    (
        "Бобровиця",
        "https://news.google.com/rss/search?q="
        + quote("Бобровиця Чернігівська область")
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),
]


# ============================================================
# ІСТОРІЯ
# ============================================================

HISTORY = [
    (
        "📚 КОЗЕЛЕЦЬ",
        "Козелець — історичне містечко Чернігівщини, відоме архітектурною спадщиною та пам'ятками козацької доби."
    ),
    (
        "📚 ОСТЕР",
        "Остер — одне з давніх міст Чернігівщини, розташоване на річці Остер."
    ),
    (
        "📚 БОБРОВИЦЯ",
        "Бобровиця — місто Чернігівської області з давньою історією та залізничним сполученням."
    ),
    (
        "📚 КОЗЕЛЕЧЧИНА",
        "Козелеччина поєднує історичні населені пункти, природні території та культурну спадщину Чернігівщини."
    ),
]


# ============================================================
# ЛОГ
# ============================================================

def log(text):
    print(text, flush=True)


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": "KozeletsAlarmBot/2.0"
})


# ============================================================
# СТАН
# ============================================================

DEFAULT_STATE = {
    "alert": {
        "active": False,
        "last_change": None,
        "last_type": None,
    },

    "news_seen": [],

    "history_index": 0,
    "history_last": None,

    "pinned_message_id": None,

    "threat_seen": [],

    "promotion": {
        "last_time": None,
        "index": 0,
    },

    "weather": {
        "data": None,
        "last_update": None,
    },

    "dashboard_last": None,
}


def create_default_state():
    return json.loads(
        json.dumps(DEFAULT_STATE)
    )


def load_state():

    if not STATE_FILE.exists():
        return create_default_state()

    try:

        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        state = create_default_state()

        if isinstance(data, dict):

            for key in state:

                if key in data:
                    state[key] = data[key]

        return state

    except Exception as e:

        log(
            f"⚠️ Помилка читання "
            f"bot_state.json: {e}"
        )

        return create_default_state()


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

        temp.replace(STATE_FILE)

    except Exception as e:

        log(
            f"⚠️ Помилка збереження "
            f"state: {e}"
        )


# ============================================================
# TELEGRAM
# ============================================================

def telegram(method, payload=None):

    if not BOT_TOKEN:

        log(
            "❌ BOT_TOKEN не заданий."
        )

        return None

    try:

        response = SESSION.post(
            f"{TELEGRAM_API}/{method}",
            json=payload or {},
            timeout=TIMEOUT
        )

        if not response.ok:

            log(
                f"❌ Telegram HTTP "
                f"{response.status_code}: "
                f"{response.text[:300]}"
            )

            return None

        data = response.json()

        if not data.get("ok"):

            log(
                f"❌ Telegram API error: "
                f"{data}"
            )

            return None

        return data.get("result")

    except requests.RequestException as e:

        log(
            f"❌ Telegram network error: "
            f"{e}"
        )

        return None

    except Exception as e:

        log(
            f"❌ Telegram error: "
            f"{e}"
        )

        return None


def send_message(text):

    if len(text) > 4090:
        text = text[:4080] + "\n…"

    return telegram(
        "sendMessage",
        {
            "chat_id": CHANNEL,
            "text": text,
            "disable_web_page_preview": True,
        }
    )


def edit_message(message_id, text):

    if len(text) > 4090:
        text = text[:4080] + "\n…"

    return telegram(
        "editMessageText",
        {
            "chat_id": CHANNEL,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
        }
    )


def pin_message(message_id):

    return telegram(
        "pinChatMessage",
        {
            "chat_id": CHANNEL,
            "message_id": message_id,
            "disable_notification": True,
        }
    )


# ============================================================
# UKRAINE ALARM
# ============================================================

def alarm_headers():

    return {
        "Authorization": UKRAINE_ALARM_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "KozeletsAlarmBot/2.0",
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

        response = SESSION.get(
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
                f"{response.status_code}"
            )

            return None

        return response.json()

    except requests.RequestException as e:

        log(
            f"❌ UkraineAlarm network "
            f"error: {e}"
        )

        return None

    except Exception as e:

        log(
            f"❌ UkraineAlarm error: "
            f"{e}"
        )

        return None


def extract_active_alerts(data):

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    active = data.get(
        "activeAlerts"
    )

    if isinstance(active, list):
        return active

    for key in (
        "alerts",
        "active_alerts",
        "items",
        "data",
    ):

        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


def alert_is_active(data):

    if data is None:
        return False

    active_alerts = (
        extract_active_alerts(data)
    )

    if active_alerts:
        return True

    if isinstance(data, dict):

        for key in (
            "active",
            "isActive",
            "is_active",
            "alert",
        ):

            value = data.get(key)

            if isinstance(value, bool):

                if value:
                    return True

            if str(value).lower() in (
                "true",
                "1",
                "active",
            ):

                return True

    return False


def get_alert_type(data):

    alerts = (
        extract_active_alerts(data)
    )

    if not alerts:
        return "Повітряна тривога"

    first = alerts[0]

    if isinstance(first, dict):

        for key in (
            "type",
            "alertType",
            "alarmType",
            "name",
        ):

            value = first.get(key)

            if value:
                return str(value)

    return "Повітряна тривога"


# ============================================================
# ПОВІТРЯНА ТРИВОГА
# ============================================================

def process_alarm(state):

    log(
        "🚨 Перевіряю повітряну "
        "тривогу..."
    )

    if not UKRAINE_ALARM_API_KEY:

        log(
            "⚠️ API ключ UkraineAlarm "
            "не заданий."
        )

        return

    data = get_chernihiv_alert()

    if data is None:
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

    now = datetime.now().strftime(
        "%d.%m.%Y %H:%M:%S"
    )

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
            state["alert"]["last_type"] = alert_type

            save_state(state)

            log(
                "🚨 Початок тривоги "
                "НАДІСЛАНО."
            )

    elif not active and old_active:

        message = (
            "🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
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
            state["alert"]["last_type"] = "end"

            save_state(state)

            log(
                "🟢 Відбій тривоги "
                "НАДІСЛАНО."
            )

    else:

        if (
            state["alert"].get(
                "active"
            )
            != active
        ):

            state["alert"]["active"] = active

            save_state(state)


# ============================================================
# NEPTUN
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    R = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    d_phi = math.radians(
        lat2 - lat1
    )

    d_lambda = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(d_lambda / 2) ** 2
    )

    return (
        2
        * R
        * math.asin(
            math.sqrt(a)
        )
    )


def get_neptun_threats():

    try:

        response = SESSION.get(
            NEPTUN_API,
            timeout=TIMEOUT
        )

        if not response.ok:

            log(
                f"⚠️ NEPTUN HTTP "
                f"{response.status_code}"
            )

            return []

        data = response.json()

        if isinstance(data, dict):

            threats = data.get(
                "threats"
            )

            if isinstance(
                threats,
                list
            ):

                return threats

        return []

    except requests.RequestException as e:

        log(
            f"⚠️ NEPTUN network "
            f"error: {e}"
        )

        return []

    except Exception as e:

        log(
            f"⚠️ NEPTUN error: "
            f"{e}"
        )

        return []


def threat_type_name(threat):

    threat_type = str(
        threat.get(
            "type",
            ""
        )
    ).lower()

    title = str(
        threat.get(
            "title",
            ""
        )
    ).lower()

    text = (
        threat_type
        + " "
        + title
    )

    if (
        "uav" in text
        or "shahed" in text
        or "шахед" in text
        or "бпла" in text
        or "дрон" in text
    ):

        return "БпЛА / Шахед"

    if "ballistic" in text:

        return "Балістична ракета"

    if (
        "missile" in text
        or "рак" in text
    ):

        return "Ракета"

    if "kab" in text:

        return "КАБ"

    return (
        threat.get("title")
        or threat.get("type")
        or "Повітряна загроза"
    )


def process_neptun(state):

    log(
        "🛰 Перевіряю NEPTUN "
        "(радіус 30 км)..."
    )

    threats = get_neptun_threats()

    seen = set(
        state.get(
            "threat_seen",
            []
        )
    )

    new_seen = []

    for threat in threats:

        if not isinstance(
            threat,
            dict
        ):
            continue

        status = str(
            threat.get(
                "status",
                "active"
            )
        ).lower()

        if status not in (
            "",
            "active"
        ):
            continue

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

        except Exception:

            continue

        distance_kozelets = (
            haversine_km(
                KOZELETS_LAT,
                KOZELETS_LON,
                lat,
                lon
            )
        )

        distance_oster = (
            haversine_km(
                OSTER_LAT,
                OSTER_LON,
                lat,
                lon
            )
        )

        distance = min(
            distance_kozelets,
            distance_oster
        )

        if distance > THREAT_RADIUS_KM:
            continue

        threat_id = str(
            threat.get("id")
            or hashlib.sha256(
                json.dumps(
                    threat,
                    ensure_ascii=False,
                    sort_keys=True
                ).encode("utf-8")
            ).hexdigest()[:24]
        )

        new_seen.append(
            threat_id
        )

        if threat_id in seen:
            continue

        name = threat_type_name(
            threat
        )

        locality = (
            threat.get("locality")
            or threat.get("district")
            or threat.get("region")
            or "невідомо"
        )

        confidence = (
            threat.get(
                "confidenceLevel"
            )
            or "невідомо"
        )

        source_count = (
            threat.get(
                "sourceCount"
            )
            or 0
        )

        heading = threat.get(
            "heading"
        )

        velocity = threat.get(
            "velocity"
        )

        speed = None

        if isinstance(
            velocity,
            dict
        ):

            speed = velocity.get(
                "speedKmh"
            )

        message = (
            "🛰 ПОВІТРЯНА ЗАГРОЗА NEPTUN\n\n"
            f"⚠️ Тип: {name}\n"
            f"📍 Район: {locality}\n"
            f"📏 Відстань: приблизно "
            f"{distance:.1f} км\n"
            f"🎯 Достовірність: {confidence}\n"
            f"📡 Джерел: {source_count}"
        )

        if heading is not None:

            message += (
                f"\n🧭 Курс: {heading}°"
            )

        if speed is not None:

            message += (
                f"\n💨 Швидкість: "
                f"{speed} км/год"
            )

        message += (
            "\n\n"
            "⚠️ Це інформація NEPTUN, "
            "а не офіційний сигнал тривоги.\n"
            "У разі офіційної тривоги "
            "дійте відповідно до офіційних "
            "повідомлень."
        )

        result = send_message(
            message
        )

        if result:

            log(
                "🚨 NEPTUN: "
                "повідомлення НАДІСЛАНО."
            )

    combined = list(
        dict.fromkeys(
            list(seen)
            + new_seen
        )
    )

    state["threat_seen"] = (
        combined[-500:]
    )

    save_state(state)


# ============================================================
# ПОГОДА
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

        response = SESSION.get(
            url,
            timeout=NEWS_TIMEOUT
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:

        log(
            f"⚠️ Weather error: "
            f"{e}"
        )

        return None


def get_cached_weather(state):

    weather_state = state.get(
        "weather",
        {}
    )

    last_update = (
        weather_state.get(
            "last_update"
        )
    )

    if last_update:

        try:

            last_dt = (
                datetime.fromisoformat(
                    last_update
                )
            )

            elapsed = (
                datetime.now(
                    timezone.utc
                )
                - last_dt
            ).total_seconds()

            if elapsed < WEATHER_INTERVAL:

                return weather_state.get(
                    "data"
                )

        except Exception:
            pass

    weather = get_weather()

    if weather:

        state["weather"] = {
            "data": weather,
            "last_update": datetime.now(
                timezone.utc
            ).isoformat()
        }

        save_state(state)

        return weather

    return weather_state.get(
        "data"
    )


def weather_description(code):

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
        99: "гроза з градом",
    }

    return descriptions.get(
        code,
        "невідомо"
    )


# ============================================================
# НОВИНИ
# ============================================================

def clean_text(text):

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


def make_news_id(
    title,
    link
):

    return hashlib.sha256(
        f"{title}|{link}".encode(
            "utf-8"
        )
    ).hexdigest()[:24]


def get_entry_datetime(entry):

    for key in (
        "published_parsed",
        "updated_parsed",
    ):

        parsed = entry.get(
            key
        )

        if parsed:

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
                pass

    return None


def get_news(state):

    log(
        "📰 Перевіряю новини "
        "за останні 30 хвилин..."
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

    for category, url in NEWS_FEEDS:

        try:

            response = SESSION.get(
                url,
                timeout=NEWS_TIMEOUT
            )

            if not response.ok:

                log(
                    f"⚠️ Google News "
                    f"{category}: HTTP "
                    f"{response.status_code}"
                )

                continue

            feed = feedparser.parse(
                response.content
            )

            for entry in feed.entries[:15]:

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

                published_at = (
                    get_entry_datetime(
                        entry
                    )
                )

                if published_at is None:
                    continue

                age_seconds = (
                    now_utc
                    - published_at
                ).total_seconds()

                # Майбутні записи
                if age_seconds < -120:
                    continue

                # Старші 30 хвилин
                if (
                    age_seconds
                    > NEWS_MAX_AGE_MINUTES * 60
                ):
                    continue

                news_id = make_news_id(
                    title,
                    link
                )

                if news_id in seen:
                    continue

                collected.append(
                    (
                        category,
                        title,
                        link,
                        news_id,
                        published_at
                    )
                )

        except requests.RequestException as e:

            log(
                f"⚠️ News network "
                f"error {category}: "
                f"{e}"
            )

        except Exception as e:

            log(
                f"⚠️ News error "
                f"{category}: "
                f"{e}"
            )

    collected.sort(
        key=lambda item: item[4],
        reverse=True
    )

    # Максимум 5 новин за один цикл
    collected = collected[:5]

    published = 0

    for (
        category,
        title,
        link,
        news_id,
        published_at
    ) in collected:

        age_minutes = int(
            max(
                0,
                (
                    now_utc
                    - published_at
                ).total_seconds()
                / 60
            )
        )

        message = (
            f"📰 {category}\n\n"
            f"🔹 {title}\n\n"
            f"🕐 Опубліковано "
            f"{age_minutes} хв тому\n\n"
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
                f"📰 Опубліковано: "
                f"{category} — {title}"
            )

    state["news_seen"] = list(
        seen
    )[-500:]

    save_state(state)

    log(
        f"📰 Нових свіжих новин: "
        f"{published}"
    )


# ============================================================
# ПРОМО
# ============================================================

def process_promotion(state):

    promo_state = state.get(
        PROMO_STATE_KEY,
        {}
    )

    last_time_str = (
        promo_state.get(
            "last_time"
        )
    )

    index = int(
        promo_state.get(
            "index",
            0
        )
    )

    now = datetime.now()

    if last_time_str:

        try:

            last_dt = datetime.strptime(
                last_time_str,
                "%Y-%m-%d %H:%M:%S"
            )

            if (
                now - last_dt
                < timedelta(
                    hours=PROMO_INTERVAL_HOURS
                )
            ):

                return

        except Exception:

            pass

    log(
        "📢 Час для промо-посту."
    )

    message = PROMO_MESSAGES[
        index % len(PROMO_MESSAGES)
    ]

    result = send_message(
        message
    )

    if result:

        promo_state[
            "last_time"
        ] = now.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        promo_state[
            "index"
        ] = (
            index + 1
        ) % len(PROMO_MESSAGES)

        state[
            PROMO_STATE_KEY
        ] = promo_state

        save_state(state)

        log(
            "📢 Промо-пост "
            "опубліковано."
        )


# ============================================================
# ІСТОРІЯ
# ============================================================

def history_post(state):

    last = state.get(
        "history_last"
    )

    now = datetime.now()

    if last:

        try:

            last_dt = datetime.strptime(
                last,
                "%Y-%m-%d %H:%M:%S"
            )

            if (
                now - last_dt
                < timedelta(
                    hours=HISTORY_INTERVAL_HOURS
                )
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

        state[
            "history_index"
        ] = index + 1

        state[
            "history_last"
        ] = now.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        save_state(state)

        log(
            "📚 Історичний пост "
            "опубліковано."
        )


# ============================================================
# ІНФОРМАЦІЙНІ БЛОКИ
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
# ПАНЕЛЬ
# ============================================================

def dashboard_text(state):

    weather = get_cached_weather(
        state
    )

    now = datetime.now().strftime(
        "%d.%m.%Y %H:%M"
    )

    active = bool(
        state["alert"].get(
            "active",
            False
        )
    )

    lines = [
        "📍 КОЗЕЛЕЦЬ | ОПЕРАТИВНА ПАНЕЛЬ",
        "",
        f"🕐 Оновлено: {now}",
        "",
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
    lines.append("🌤 ПОГОДА")

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
                "",
            ])

        except Exception:

            lines.extend([
                "⚠️ Дані погоди "
                "тимчасово недоступні.",
                "",
            ])

    else:

        lines.extend([
            "⚠️ Дані погоди "
            "тимчасово недоступні.",
            "",
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
        "Козелець / Остер / Бобровиця",
        "📰 Свіжість новин: "
        "до 30 хвилин",
        "",
        "🚨 Тривоги: кожну 1 хвилину",
        "🛰 NEPTUN: кожну 1 хвилину",
        "📰 Новини: кожну 1 хвилину",
        "📌 Панель: кожні 5 хвилин",
    ])

    return "\n".join(
        lines
    )


def update_dashboard(state):

    log(
        "📌 Перевіряю оперативну панель..."
    )

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

    result = send_message(
        text
    )

    if not result:
        return

    new_id = result.get(
        "message_id"
    )

    if not new_id:
        return

    state[
        "pinned_message_id"
    ] = new_id

    save_state(state)

    pin_message(
        new_id
    )

    log(
        "📌 Панель створена "
        "та закріплена."
    )


# ============================================================
# ГОЛОВНИЙ ЦИКЛ
# ============================================================

def main():

    log("")
    log("=" * 60)
    log("🤖 KOZELETS ALARM BOT")
    log("=" * 60)

    log(
        datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )
    )

    log(
        "⚙️ Перевірка: кожну 1 хвилину"
    )

    log(
        "📰 Новини: до 30 хвилин"
    )

    log(
        "🛰 NEPTUN: радіус 30 км"
    )

    log("=" * 60)

    if not BOT_TOKEN:

        log(
            "❌ КРИТИЧНА ПОМИЛКА: "
            "BOT_TOKEN не заданий."
        )

        return

    if not UKRAINE_ALARM_API_KEY:

        log(
            "⚠️ УВАГА: "
            "UKRAINE_ALARM_API_KEY "
            "не заданий."
        )

    state = load_state()

    last_dashboard = 0
    last_promotion_check = 0
    last_history_check = 0

    while True:

        cycle_start = time.monotonic()

        try:

            state = load_state()

            # ------------------------------------------------
            # 1. ПОВІТРЯНА ТРИВОГА
            # ------------------------------------------------

            process_alarm(
                state
            )

            # ------------------------------------------------
            # 2. NEPTUN
            # ------------------------------------------------

            process_neptun(
                state
            )

            # ------------------------------------------------
            # 3. НОВИНИ
            # ------------------------------------------------

            get_news(
                state
            )

            current_time = time.monotonic()

            # ------------------------------------------------
            # 4. ПРОМО
            # ------------------------------------------------

            if (
                current_time
                - last_promotion_check
                >= 600
            ):

                process_promotion(
                    state
                )

                last_promotion_check = (
                    current_time
                )

            # ------------------------------------------------
            # 5. ІСТОРІЯ
            # ------------------------------------------------

            if (
                current_time
                - last_history_check
                >= 1800
            ):

                history_post(
                    state
                )

                last_history_check = (
                    current_time
                )

            # ------------------------------------------------
            # 6. ПАНЕЛЬ
            # ------------------------------------------------

            if (
                current_time
                - last_dashboard
                >= DASHBOARD_INTERVAL
            ):

                update_dashboard(
                    state
                )

                last_dashboard = (
                    current_time
                )

            # ------------------------------------------------
            # ЧАС ЦИКЛУ
            # ------------------------------------------------

            cycle_time = (
                time.monotonic()
                - cycle_start
            )

            log(
                f"✅ Цикл завершено "
                f"за {cycle_time:.1f} сек."
            )

        except Exception as e:

            log(
                f"⚠️ Помилка головного "
                f"циклу: {e}"
            )

        # ----------------------------------------------------
        # ЧЕКАЄМО ДО НАСТУПНОЇ ПЕРЕВІРКИ
        # ----------------------------------------------------

        cycle_time = (
            time.monotonic()
            - cycle_start
        )

        sleep_time = max(
            1,
            MAIN_LOOP_SECONDS
            - cycle_time
        )

        log(
            f"😴 Наступна перевірка "
            f"через {sleep_time:.0f} сек."
        )

        time.sleep(
            sleep_time
        )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    main()
