import os
import re
import json
import hashlib
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import feedparser


# ============================================================
# ОСНОВНІ НАЛАШТУВАННЯ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL = os.getenv("CHANNEL", "@Kozelets_Alarm").strip()

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

NEPTUN_API = "https://neptun.in.ua/api/v1/threats"

STATE_FILE = Path("bot_state.json")


# ============================================================
# ІНТЕРВАЛИ
# ============================================================

# NEPTUN перевіряється кожні 30 секунд
NEPTUN_INTERVAL = 30

# Статус активної загрози оновлюється кожні 5 хвилин
THREAT_STATUS_INTERVAL = 300

# Новини кожні 30 хвилин
NEWS_INTERVAL = 1800

# Новини максимум 30 хвилин від моменту публікації
NEWS_MAX_AGE = 30

# Погода кожні 10 хвилин
WEATHER_INTERVAL = 600

# Оперативна панель кожні 10 хвилин
DASHBOARD_INTERVAL = 600

# Реклама кожні 6 годин
PROMO_INTERVAL = 21600

# Історія кожні 12 годин
HISTORY_INTERVAL = 43200

# HTTP timeout
API_TIMEOUT = 7
NEWS_TIMEOUT = 7


# ============================================================
# КООРДИНАТИ
# ============================================================

KOZELETS_LAT = 50.913
KOZELETS_LON = 31.121

OSTER_LAT = 50.950
OSTER_LON = 30.883

BOBROVYTSIA_LAT = 50.750
BOBROVYTSIA_LON = 31.383

KIPTI_LAT = 51.050
KIPTI_LON = 31.150


# ============================================================
# РАДІУС ВИЯВЛЕННЯ
# ============================================================

THREAT_RADIUS_KM = 50


# ============================================================
# НАЗВИ ЛОКАЦІЙ
# ============================================================

LOCALITIES = {
    "КІПТІ": (KIPTI_LAT, KIPTI_LON),
    "КОЗЕЛЕЦЬ": (KOZELETS_LAT, KOZELETS_LON),
    "ОСТЕР": (OSTER_LAT, OSTER_LON),
    "БОБРОВИЦЯ": (BOBROVYTSIA_LAT, BOBROVYTSIA_LON),
}


# ============================================================
# ПРОМО
# ============================================================

PROMO_MESSAGES = [
    (
        "📢 КОРИСНИЙ МІСЦЕВИЙ КАНАЛ\n\n"
        "🚨 Повітряні загрози та важливі повідомлення\n"
        "📰 Свіжі місцеві новини\n"
        "🌤 Погода\n"
        "📍 Козелець, Остер, Бобровиця та Чернігівщина\n\n"
        "👉 https://t.me/Kozelets_Alarm\n\n"
        "📲 Перешліть канал рідним та друзям."
    ),
    (
        "📍 КОЗЕЛЕЦЬ | ОСТЕР | БОБРОВИЦЯ\n\n"
        "🚨 Важливі повідомлення\n"
        "📰 Місцеві новини\n"
        "🌤 Погода\n\n"
        "Підписуйтесь на канал:\n"
        "👉 https://t.me/Kozelets_Alarm"
    ),
    (
        "🔔 НЕ ПРОПУСКАЙТЕ ВАЖЛИВЕ\n\n"
        "Канал «Козелець Повітряна Тривога!»\n\n"
        "🚨 Повітряні загрози\n"
        "📰 Новини\n"
        "🌤 Погода\n"
        "📍 Козелець та Чернігівщина\n\n"
        "👉 https://t.me/Kozelets_Alarm"
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
        "Козелець — історичне містечко Чернігівщини, відоме своєю архітектурною спадщиною."
    ),

    (
        "📚 ОСТЕР",
        "Остер — одне з давніх міст Чернігівщини, розташоване на річці Остер."
    ),

    (
        "📚 БОБРОВИЦЯ",
        "Бобровиця — місто Чернігівської області з давньою історією."
    ),

    (
        "📚 КОЗЕЛЕЧЧИНА",
        "Козелеччина поєднує історичні населені пункти, природні території та культурну спадщину Чернігівщини."
    ),
]


# ============================================================
# LOG
# ============================================================

def log(text):
    print(text, flush=True)


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": "KozeletsAlarmBot/4.0"
})


# ============================================================
# СТАН БОТА
# ============================================================

DEFAULT_STATE = {
    "active_threats": {},
    "threat_status": False,
    "last_status_time": None,

    "news_seen": [],

    "promotion": {
        "index": 0,
        "last_time": None
    },

    "history_index": 0,
    "history_last": None,

    "weather": {
        "data": None,
        "last_update": None
    },

    "pinned_message_id": None
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
            f"⚠️ Помилка читання state: {e}"
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

        temp.replace(
            STATE_FILE
        )

    except Exception as e:

        log(
            f"⚠️ Помилка збереження state: {e}"
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
            timeout=API_TIMEOUT
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
                f"❌ Telegram API error: {data}"
            )

            return None

        return data.get("result")

    except requests.RequestException as e:

        log(
            f"❌ Telegram network error: {e}"
        )

        return None

    except Exception as e:

        log(
            f"❌ Telegram error: {e}"
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
            "disable_web_page_preview": True
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
            "disable_web_page_preview": True
        }
    )


def pin_message(message_id):

    return telegram(
        "pinChatMessage",
        {
            "chat_id": CHANNEL,
            "message_id": message_id,
            "disable_notification": True
        }
    )


# ============================================================
# МАТЕМАТИКА
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    radius = 6371.0

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
        +
        math.cos(phi1)
        * math.cos(phi2)
        * math.sin(d_lambda / 2) ** 2
    )

    return (
        2
        * radius
        * math.asin(
            math.sqrt(a)
        )
    )


def bearing_degrees(
    lat1,
    lon1,
    lat2,
    lon2
):

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    diff_lon = math.radians(
        lon2 - lon1
    )

    x = (
        math.sin(diff_lon)
        * math.cos(lat2)
    )

    y = (
        math.cos(lat1)
        * math.sin(lat2)
        -
        math.sin(lat1)
        * math.cos(lat2)
        * math.cos(diff_lon)
    )

    bearing = math.degrees(
        math.atan2(x, y)
    )

    return (
        bearing + 360
    ) % 360


def angle_difference(
    a,
    b
):

    difference = abs(
        a - b
    ) % 360

    if difference > 180:
        difference = 360 - difference

    return difference


# ============================================================
# NEPTUN
# ============================================================

def get_neptun_threats():

    try:

        response = SESSION.get(
            NEPTUN_API,
            timeout=API_TIMEOUT
        )

        if not response.ok:

            log(
                f"⚠️ NEPTUN HTTP "
                f"{response.status_code}"
            )

            return []

        data = response.json()

        if isinstance(data, list):
            return data

        if isinstance(data, dict):

            for key in (
                "threats",
                "data",
                "items",
                "results"
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

    except requests.RequestException as e:

        log(
            f"⚠️ NEPTUN network error: {e}"
        )

        return []

    except Exception as e:

        log(
            f"⚠️ NEPTUN error: {e}"
        )

        return []


def get_threat_coordinates(
    threat
):

    lat = (
        threat.get("lat")
        or threat.get("latitude")
    )

    lon = (
        threat.get("lon")
        or threat.get("longitude")
        or threat.get("lng")
    )

    if lat is None or lon is None:
        return None

    try:

        return (
            float(lat),
            float(lon)
        )

    except Exception:

        return None


def get_threat_id(
    threat
):

    value = (
        threat.get("id")
        or threat.get("uuid")
        or threat.get("threatId")
    )

    if value:
        return str(value)

    raw = json.dumps(
        threat,
        ensure_ascii=False,
        sort_keys=True
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]


def get_threat_heading(
    threat
):

    for key in (
        "heading",
        "course",
        "direction",
        "azimuth"
    ):

        value = threat.get(
            key
        )

        if value is not None:

            try:
                return float(value)

            except Exception:
                pass

    velocity = threat.get(
        "velocity"
    )

    if isinstance(
        velocity,
        dict
    ):

        for key in (
            "heading",
            "course",
            "direction",
            "azimuth"
        ):

            value = velocity.get(
                key
            )

            if value is not None:

                try:
                    return float(value)

                except Exception:
                    pass

    return None


def threat_is_active(
    threat
):

    status = str(
        threat.get(
            "status",
            "active"
        )
    ).lower()

    return status in (
        "",
        "active",
        "detected",
        "tracking"
    )


def get_nearest_locality(
    lat,
    lon
):

    nearest_name = None
    nearest_distance = 999999

    for name, coords in LOCALITIES.items():

        distance = haversine_km(
            lat,
            lon,
            coords[0],
            coords[1]
        )

        if distance < nearest_distance:

            nearest_distance = distance
            nearest_name = name

    return (
        nearest_name,
        nearest_distance
    )


# ============================================================
# ВИЗНАЧЕННЯ НАПРЯМКУ НА КОЗЕЛЕЦЬ
# ============================================================

def is_heading_to_kozelets(
    lat,
    lon,
    heading
):

    if heading is None:
        return False

    required_bearing = bearing_degrees(
        lat,
        lon,
        KOZELETS_LAT,
        KOZELETS_LON
    )

    difference = angle_difference(
        heading,
        required_bearing
    )

    # Допускаємо відхилення приблизно 45°
    return difference <= 45


# ============================================================
# ФОРМУВАННЯ ПОВІДОМЛЕННЯ NEPTUN
# ============================================================

def build_threat_message(
    threat,
    lat,
    lon,
    heading
):

    toward_kozelets = (
        is_heading_to_kozelets(
            lat,
            lon,
            heading
        )
    )

    # Основне коротке повідомлення
    if toward_kozelets:

        return (
            "🚨 ПОВІТРЯНА НЕБЕЗПЕКА\n\n"
            "📍 КІПТІ → КОЗЕЛЕЦЬ → ОСТЕР → БОБРОВИЦЯ\n"
            "🧭 У НАПРЯМКУ КОЗЕЛЬЦЯ\n\n"
            "⚠️ Слідкуйте за офіційними повідомленнями."
        )

    return (
        "🚨 ПОВІТРЯНА НЕБЕЗПЕКА\n\n"
        "📍 КІПТІ → КОЗЕЛЕЦЬ → ОСТЕР → БОБРОВИЦЯ\n\n"
        "⚠️ Слідкуйте за офіційними повідомленнями."
    )


# ============================================================
# ОБРОБКА NEPTUN
# ============================================================

def process_neptun(
    state,
    force_status=False
):

    log(
        "🛰 Перевіряю NEPTUN..."
    )

    threats = get_neptun_threats()

    current_threats = {}

    for threat in threats:

        if not isinstance(
            threat,
            dict
        ):
            continue

        if not threat_is_active(
            threat
        ):
            continue

        coordinates = (
            get_threat_coordinates(
                threat
            )
        )

        if coordinates is None:
            continue

        lat, lon = coordinates

        distance_kozelets = (
            haversine_km(
                lat,
                lon,
                KOZELETS_LAT,
                KOZELETS_LON
            )
        )

        distance_oster = (
            haversine_km(
                lat,
                lon,
                OSTER_LAT,
                OSTER_LON
            )
        )

        distance_bobrov = (
            haversine_km(
                lat,
                lon,
                BOBROVYTSIA_LAT,
                BOBROVYTSIA_LON
            )
        )

        distance_kipti = (
            haversine_km(
                lat,
                lon,
                KIPTI_LAT,
                KIPTI_LON
            )
        )

        nearest_distance = min(
            distance_kozelets,
            distance_oster,
            distance_bobrov,
            distance_kipti
        )

        if nearest_distance > THREAT_RADIUS_KM:
            continue

        threat_id = get_threat_id(
            threat
        )

        heading = get_threat_heading(
            threat
        )

        current_threats[
            threat_id
        ] = {
            "lat": lat,
            "lon": lon,
            "heading": heading
        }

    previous_threats = state.get(
        "active_threats",
        {}
    )

    # ========================================================
    # НОВА ЗАГРОЗА
    # ========================================================

    for threat_id, info in current_threats.items():

        if threat_id in previous_threats:
            continue

        message = build_threat_message(
            {},
            info["lat"],
            info["lon"],
            info["heading"]
        )

        result = send_message(
            message
        )

        if result:

            log(
                "🚨 NEPTUN: нова "
                "повітряна небезпека "
                "НАДІСЛАНА."
            )

    # ========================================================
    # ВИЗНАЧАЄМО ЗАГАЛЬНИЙ СТАТУС
    # ========================================================

    old_status = bool(
        state.get(
            "threat_status",
            False
        )
    )

    new_status = bool(
        current_threats
    )

    now = datetime.now(
        timezone.utc
    )

    # ========================================================
    # ПОЧАТОК НЕБЕЗПЕКИ
    # ========================================================

    if new_status and not old_status:

        state["threat_status"] = True

        state["last_status_time"] = (
            now.isoformat()
        )

        log(
            "🔴 NEPTUN: небезпека "
            "АКТИВНА."
        )

    # ========================================================
    # ВІДБІЙ
    # ========================================================

    elif not new_status and old_status:

        send_message(
            "🟢 НЕБЕЗПЕКА ЗАВЕРШИЛАСЯ\n\n"
            "📍 КІПТІ → КОЗЕЛЕЦЬ → ОСТЕР → БОБРОВИЦЯ\n\n"
            "Стан NEPTUN більше не показує "
            "активної загрози в заданій зоні."
        )

        state["threat_status"] = False

        state["last_status_time"] = (
            now.isoformat()
        )

        log(
            "🟢 NEPTUN: небезпека "
            "завершилась."
        )

    # ========================================================
    # ОНОВЛЕННЯ СТАТУСУ КОЖНІ 5 ХВИЛИН
    # ========================================================

    elif (
        new_status
        and force_status
    ):

        send_message(
            "🔴 СТАТУС НЕБЕЗПЕКИ\n\n"
            "📍 КІПТІ → КОЗЕЛЕЦЬ → ОСТЕР → БОБРОВИЦЯ\n\n"
            "⚠️ Небезпека залишається активною.\n"
            "🛰 Дані NEPTUN оновлено."
        )

        state["last_status_time"] = (
            now.isoformat()
        )

        log(
            "🔄 Статус небезпеки "
            "оновлено."
        )

    state["active_threats"] = (
        current_threats
    )

    save_state(state)

    return new_status


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
        "weather_code,"
        "wind_speed_10m,"
        "wind_direction_10m"
        "&timezone=Europe%2FKyiv"
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
            f"⚠️ Weather error: {e}"
        )

        return None


def get_cached_weather(
    state
):

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

            last_dt = datetime.fromisoformat(
                last_update
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
        51: "мряка",
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
# NEWS
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


def get_entry_datetime(
    entry
):

    for key in (
        "published_parsed",
        "updated_parsed"
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


def get_news(
    state
):

    log(
        "📰 Перевіряю новини..."
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
                continue

            feed = feedparser.parse(
                response.content
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

                if age_seconds < -120:
                    continue

                if age_seconds > (
                    NEWS_MAX_AGE * 60
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

        except Exception as e:

            log(
                f"⚠️ News error "
                f"{category}: {e}"
            )

    collected.sort(
        key=lambda x: x[4],
        reverse=True
    )

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
            f"🕐 {age_minutes} хв тому\n\n"
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

    state["news_seen"] = list(
        seen
    )[-500:]

    save_state(state)

    log(
        f"📰 Нових новин: {published}"
    )


# ============================================================
# ПРОМО
# ============================================================

def process_promotion(
    state
):

    promo = state.get(
        "promotion",
        {}
    )

    last_time = promo.get(
        "last_time"
    )

    index = int(
        promo.get(
            "index",
            0
        )
    )

    now = datetime.now()

    if last_time:

        try:

            last_dt = datetime.strptime(
                last_time,
                "%Y-%m-%d %H:%M:%S"
            )

            if (
                now - last_dt
            ).total_seconds() < PROMO_INTERVAL:

                return

        except Exception:

            pass

    message = PROMO_MESSAGES[
        index % len(PROMO_MESSAGES)
    ]

    result = send_message(
        message
    )

    if result:

        state["promotion"] = {
            "index": (
                index + 1
            ) % len(PROMO_MESSAGES),

            "last_time": now.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        }

        save_state(state)

        log(
            "📢 Реклама опублікована."
        )


# ============================================================
# HISTORY
# ============================================================

def process_history(
    state
):

    last_time = state.get(
        "history_last"
    )

    now = datetime.now()

    if last_time:

        try:

            last_dt = datetime.strptime(
                last_time,
                "%Y-%m-%d %H:%M:%S"
            )

            if (
                now - last_dt
            ).total_seconds() < HISTORY_INTERVAL:

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

    result = send_message(
        f"{title}\n\n{text}\n\n"
        "📍 Чернігівщина"
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

        save_state(state)

        log(
            "📚 Історичний пост "
            "опубліковано."
        )


# ============================================================
# DASHBOARD
# ============================================================

def dashboard_text(
    state
):

    weather = get_cached_weather(
        state
    )

    active = bool(
        state.get(
            "threat_status",
            False
        )
    )

    now = datetime.now().strftime(
        "%d.%m.%Y %H:%M"
    )

    lines = [
        "📍 КОЗЕЛЕЦЬ | ОПЕРАТИВНА ПАНЕЛЬ",
        "",
        f"🕐 Оновлено: {now}",
        ""
    ]

    if active:

        lines.append(
            "🚨 СТАТУС: 🔴 НЕБЕЗПЕКА"
        )

    else:

        lines.append(
            "🟢 СТАТУС: БЕЗ АКТИВНОЇ ЗАГРОЗИ"
        )

    lines.extend([
        "",
        "📍 ЗОНА:",
        "КІПТІ → КОЗЕЛЕЦЬ → ОСТЕР → БОБРОВИЦЯ",
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

            lines.extend([
                f"🌡 Температура: "
                f"{current.get('temperature_2m')} °C",

                f"🌡 Відчувається: "
                f"{current.get('apparent_temperature')} °C",

                f"💧 Вологість: "
                f"{current.get('relative_humidity_2m')}%",

                f"💨 Вітер: "
                f"{current.get('wind_speed_10m')} км/год",

                f"☁️ "
                f"{weather_description(current.get('weather_code'))}",

                ""
            ])

        except Exception:

            lines.append(
                "⚠️ Погода недоступна."
            )

    else:

        lines.append(
            "⚠️ Погода недоступна."
        )

    lines.extend([
        "",
        "📰 Новини: кожні 30 хв",
        "🛰 NEPTUN: кожні 30 сек",
        "🔄 Статус небезпеки: кожні 5 хв",
        "📢 Реклама: кожні 6 год",
        "📚 Історія: кожні 12 год"
    ])

    return "\n".join(
        lines
    )


def update_dashboard(
    state
):

    log(
        "📌 Оновлюю панель..."
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

        state[
            "pinned_message_id"
        ] = None

        save_state(state)

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
# MAIN
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
        "🛰 NEPTUN: кожні 30 секунд"
    )

    log(
        "🔄 Статус: кожні 5 хвилин"
    )

    log(
        "📰 Новини: кожні 30 хвилин"
    )

    log(
        "📢 Реклама: кожні 6 годин"
    )

    log(
        "📚 Історія: кожні 12 годин"
    )

    log("=" * 60)

    if not BOT_TOKEN:

        log(
            "❌ BOT_TOKEN не заданий."
        )

        return

    state = load_state()

    # ========================================================
    # ПЕРШИЙ ЗАПУСК — БЕЗ ОЧІКУВАННЯ
    # ========================================================

    log("")
    log(
        "🚀 ПОЧИНАЮ ПЕРШУ ПЕРЕВІРКУ..."
    )

    process_neptun(
        state,
        force_status=False
    )

    get_news(
        state
    )

    get_cached_weather(
        state
    )

    update_dashboard(
        state
    )

    now = time.monotonic()

    last_neptun = now
    last_status = now
    last_news = now
    last_weather = now
    last_dashboard = now
    last_promotion = now
    last_history = now

    log("")
    log(
        "✅ ПЕРША ПЕРЕВІРКА ЗАВЕРШЕНА."
    )
    log(
        "🤖 Бот працює у постійному режимі."
    )
    log("")

    # ========================================================
    # ПОСТІЙНИЙ ЦИКЛ
    # ========================================================

    while True:

        try:

            current = time.monotonic()

            # ------------------------------------------------
            # NEPTUN — 30 СЕКУНД
            # ------------------------------------------------

            if (
                current - last_neptun
                >= NEPTUN_INTERVAL
            ):

                process_neptun(
                    state,
                    force_status=False
                )

                last_neptun = time.monotonic()

            # ------------------------------------------------
            # СТАТУС — 5 ХВИЛИН
            # ------------------------------------------------

            if (
                current - last_status
                >= THREAT_STATUS_INTERVAL
            ):

                process_neptun(
                    state,
                    force_status=True
                )

                last_status = time.monotonic()

            # ------------------------------------------------
            # НОВИНИ — 30 ХВИЛИН
            # ------------------------------------------------

            if (
                current - last_news
                >= NEWS_INTERVAL
            ):

                get_news(
                    state
                )

                last_news = time.monotonic()

            # ------------------------------------------------
            # ПОГОДА — 10 ХВИЛИН
            # ------------------------------------------------

            if (
                current - last_weather
                >= WEATHER_INTERVAL
            ):

                get_cached_weather(
                    state
                )

                last_weather = time.monotonic()

            # ------------------------------------------------
            # ПАНЕЛЬ — 10 ХВИЛИН
            # ------------------------------------------------

            if (
                current - last_dashboard
                >= DASHBOARD_INTERVAL
            ):

                update_dashboard(
                    state
                )

                last_dashboard = time.monotonic()

            # ------------------------------------------------
            # РЕКЛАМА — 6 ГОДИН
            # ------------------------------------------------

            if (
                current - last_promotion
                >= PROMO_INTERVAL
            ):

                process_promotion(
                    state
                )

                last_promotion = time.monotonic()

            # ------------------------------------------------
            # ІСТОРІЯ — 12 ГОДИН
            # ------------------------------------------------

            if (
                current - last_history
                >= HISTORY_INTERVAL
            ):

                process_history(
                    state
                )

                last_history = time.monotonic()

        except Exception as e:

            log(
                f"⚠️ Помилка головного циклу: "
                f"{e}"
            )

        time.sleep(1)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
