import os
import time
import json
import math
import html
import hashlib
import requests
import feedparser

from pathlib import Path
from datetime import datetime, timezone, timedelta


# ============================================================
# КОЗЕЛЕЦЬ ПОВІТРЯНА ТРИВОГА — TELEGRAM BOT
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL = os.getenv("CHANNEL", "@Kozelets_Alarm").strip()

STATE_FILE = Path("bot_state.json")


# ============================================================
# НАЛАШТУВАННЯ
# ============================================================

# NEPTUN перевіряємо кожні 30 секунд,
# але повідомлення надсилаємо ТІЛЬКИ при зміні стану
NEPTUN_CHECK_SECONDS = 30

# Новини
NEWS_CHECK_SECONDS = 30 * 60
NEWS_MAX_AGE_MINUTES = 30

# Погода
WEATHER_CHECK_SECONDS = 10 * 60

# Панель
DASHBOARD_CHECK_SECONDS = 10 * 60

# Промо
PROMO_CHECK_SECONDS = 6 * 60 * 60

# Історія
HISTORY_CHECK_SECONDS = 12 * 60 * 60


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


# Радіус пошуку NEPTUN
THREAT_RADIUS_KM = 50


# ============================================================
# NEPTUN
# ============================================================

NEPTUN_API = "https://neptun.in.ua/api/v1/threats"


# ============================================================
# НОВИНИ
# ============================================================

NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=%D0%9A%D0%BE%D0%B7%D0%B5%D0%BB%D0%B5%D1%86%D1%8C&hl=uk&gl=UA&ceid=UA:uk",

    "https://news.google.com/rss/search?q=%D0%9E%D1%81%D1%82%D0%B5%D1%80+%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%B0+%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C&hl=uk&gl=UA&ceid=UA:uk",

    "https://news.google.com/rss/search?q=%D0%91%D0%BE%D0%B1%D1%80%D0%BE%D0%B2%D0%B8%D1%86%D1%8F+%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%B0+%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C&hl=uk&gl=UA&ceid=UA:uk",
]


# ============================================================
# СТАН БОТА
# ============================================================

def load_state():

    if not STATE_FILE.exists():

        return {
            "active_threats": {},
            "threat_status": False,
            "last_news_check": 0,
            "last_weather_check": 0,
            "last_dashboard_check": 0,
            "last_promo_check": 0,
            "last_history_check": 0,
            "published_news": [],
            "history": []
        }

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            state = json.load(f)

        state.setdefault(
            "active_threats",
            {}
        )

        state.setdefault(
            "threat_status",
            False
        )

        state.setdefault(
            "last_news_check",
            0
        )

        state.setdefault(
            "last_weather_check",
            0
        )

        state.setdefault(
            "last_dashboard_check",
            0
        )

        state.setdefault(
            "last_promo_check",
            0
        )

        state.setdefault(
            "last_history_check",
            0
        )

        state.setdefault(
            "published_news",
            []
        )

        state.setdefault(
            "history",
            []
        )

        return state

    except Exception:

        return {
            "active_threats": {},
            "threat_status": False,
            "last_news_check": 0,
            "last_weather_check": 0,
            "last_dashboard_check": 0,
            "last_promo_check": 0,
            "last_history_check": 0,
            "published_news": [],
            "history": []
        }


state = load_state()


def save_state():

    try:

        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:

        print(
            f"⚠️ Не вдалося зберегти стан: {e}"
        )


# ============================================================
# TELEGRAM
# ============================================================

def telegram_request(
    method,
    data
):

    if not BOT_TOKEN:

        print(
            "❌ BOT_TOKEN не заданий."
        )

        return None

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/{method}"
    )

    try:

        response = requests.post(
            url,
            data=data,
            timeout=20
        )

        if response.status_code != 200:

            print(
                f"❌ Telegram HTTP "
                f"{response.status_code}: "
                f"{response.text[:300]}"
            )

            return None

        result = response.json()

        if not result.get("ok"):

            print(
                f"❌ Telegram API: {result}"
            )

            return None

        return result

    except Exception as e:

        print(
            f"❌ Telegram помилка: {e}"
        )

        return None


def send_message(text):

    return telegram_request(
        "sendMessage",
        {
            "chat_id": CHANNEL,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
    )


# ============================================================
# ГЕОГРАФІЯ
# ============================================================

def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    r = 6371

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(
        lat2 - lat1
    )

    dl = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dp / 2) ** 2
        +
        math.cos(p1)
        *
        math.cos(p2)
        *
        math.sin(dl / 2) ** 2
    )

    return (
        2
        *
        r
        *
        math.asin(
            math.sqrt(a)
        )
    )


def bearing(
    lat1,
    lon1,
    lat2,
    lon2
):

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dl = math.radians(
        lon2 - lon1
    )

    y = (
        math.sin(dl)
        *
        math.cos(lat2)
    )

    x = (
        math.cos(lat1)
        *
        math.sin(lat2)
        -
        math.sin(lat1)
        *
        math.cos(lat2)
        *
        math.cos(dl)
    )

    angle = math.degrees(
        math.atan2(y, x)
    )

    return (
        angle + 360
    ) % 360


def is_heading_to_kozelets(
    lat,
    lon,
    heading
):

    if heading is None:

        return False

    target = bearing(
        lat,
        lon,
        KOZELETS_LAT,
        KOZELETS_LON
    )

    difference = abs(
        target - heading
    )

    if difference > 180:

        difference = (
            360 - difference
        )

    return difference <= 45


# ============================================================
# NEPTUN — ОТРИМАННЯ ДАНИХ
# ============================================================

def get_neptun_threats():

    try:

        response = requests.get(
            NEPTUN_API,
            timeout=15
        )

        if response.status_code != 200:

            return []

        data = response.json()

        if isinstance(
            data,
            list
        ):

            return data

        if isinstance(
            data,
            dict
        ):

            for key in [
                "threats",
                "data",
                "items",
                "results"
            ]:

                if isinstance(
                    data.get(key),
                    list
                ):

                    return data[key]

        return []

    except Exception:

        return []


def get_value(
    obj,
    *keys
):

    if not isinstance(
        obj,
        dict
    ):

        return None

    for key in keys:

        if key in obj:

            return obj[key]

    return None


def extract_coordinates(
    threat
):

    lat = get_value(
        threat,
        "lat",
        "latitude"
    )

    lon = get_value(
        threat,
        "lon",
        "lng",
        "longitude"
    )

    if (
        lat is not None
        and
        lon is not None
    ):

        try:

            return (
                float(lat),
                float(lon)
            )

        except Exception:

            pass

    coordinates = threat.get(
        "coordinates"
    )

    if isinstance(
        coordinates,
        dict
    ):

        lat = get_value(
            coordinates,
            "lat",
            "latitude"
        )

        lon = get_value(
            coordinates,
            "lon",
            "lng",
            "longitude"
        )

        if (
            lat is not None
            and
            lon is not None
        ):

            try:

                return (
                    float(lat),
                    float(lon)
                )

            except Exception:

                pass

    return None


def extract_heading(
    threat
):

    heading = get_value(
        threat,
        "heading",
        "direction",
        "course",
        "azimuth"
    )

    if heading is None:

        return None

    try:

        return float(
            heading
        )

    except Exception:

        return None


def threat_is_active(
    threat
):

    status = str(
        get_value(
            threat,
            "status",
            "state"
        )
        or ""
    ).lower().strip()

    if status in [
        "",
        "active",
        "detected",
        "tracking",
        "new",
        "warning"
    ]:

        return True

    if status in [
        "inactive",
        "finished",
        "ended",
        "completed",
        "expired"
    ]:

        return False

    return True


def make_threat_id(
    threat
):

    value = get_value(
        threat,
        "id",
        "uuid",
        "threat_id"
    )

    if value:

        return str(value)

    raw = json.dumps(
        threat,
        ensure_ascii=False,
        sort_keys=True
    )

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()


def get_threat_description(
    threat
):

    latlon = extract_coordinates(
        threat
    )

    if not latlon:

        return None

    lat, lon = latlon

    distance = distance_km(
        lat,
        lon,
        KOZELETS_LAT,
        KOZELETS_LON
    )

    if (
        distance
        >
        THREAT_RADIUS_KM
    ):

        return None

    heading = extract_heading(
        threat
    )

    if is_heading_to_kozelets(
        lat,
        lon,
        heading
    ):

        return "у напрямку Козельця"

    return "у районі Козельця"


# ============================================================
# NEPTUN — ПОЧАТОК / ВІДБІЙ
# ============================================================

def process_neptun():

    threats = get_neptun_threats()

    current = {}

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

        description = (
            get_threat_description(
                threat
            )
        )

        if not description:

            continue

        threat_id = make_threat_id(
            threat
        )

        current[threat_id] = {
            "description": description
        }

    old_active = bool(
        state.get(
            "active_threats"
        )
    )

    new_active = bool(
        current
    )

    # ========================================================
    # ПОЧАТОК НЕБЕЗПЕКИ
    # ========================================================

    if (
        not old_active
        and
        new_active
    ):

        directions = set()

        for item in current.values():

            directions.add(
                item["description"]
            )

        if (
            "у напрямку Козельця"
            in directions
        ):

            direction_text = (
                "🧭 Напрямок: <b>Козелець</b>"
            )

        else:

            direction_text = (
                "📍 Район: <b>Козелець</b>"
            )

        message = (
            "🚨 <b>ПОЧАТОК НЕБЕЗПЕКИ</b>\n\n"
            "За даними NEPTUN "
            "зафіксовано повітряну загрозу.\n\n"
            f"{direction_text}\n\n"
            "⚠️ Слідкуйте за офіційними повідомленнями."
        )

        result = send_message(
            message
        )

        if result:

            print(
                "🚨 NEPTUN: початок небезпеки — "
                "повідомлення надіслано."
            )

    # ========================================================
    # ВІДБІЙ
    # ========================================================

    if (
        old_active
        and
        not new_active
    ):

        message = (
            "🟢 <b>ВІДБІЙ НЕБЕЗПЕКИ</b>\n\n"
            "За даними NEPTUN "
            "активної загрози "
            "в районі Козельця не зафіксовано.\n\n"
            "⚠️ Якщо у вашому районі "
            "ще оголошена офіційна тривога, "
            "залишайтеся в безпечному місці."
        )

        result = send_message(
            message
        )

        if result:

            print(
                "🟢 NEPTUN: відбій — "
                "повідомлення надіслано."
            )

    # ========================================================
    # ЗБЕРІГАЄМО СТАН
    # ========================================================

    state["active_threats"] = current
    state["threat_status"] = new_active

    save_state()


# ============================================================
# НОВИНИ
# ============================================================

def get_news():

    result = []

    now = datetime.now(
        timezone.utc
    )

    for feed_url in NEWS_FEEDS:

        try:

            feed = feedparser.parse(
                feed_url
            )

            for entry in feed.entries:

                title = entry.get(
                    "title",
                    ""
                ).strip()

                link = entry.get(
                    "link",
                    ""
                ).strip()

                if (
                    not title
                    or
                    not link
                ):

                    continue

                published = entry.get(
                    "published_parsed"
                )

                if not published:

                    continue

                published_dt = datetime(
                    *published[:6],
                    tzinfo=timezone.utc
                )

                age = (
                    now - published_dt
                ).total_seconds() / 60

                if age < 0:

                    continue

                if (
                    age
                    >
                    NEWS_MAX_AGE_MINUTES
                ):

                    continue

                result.append({
                    "title": title,
                    "link": link,
                    "published": published_dt
                })

        except Exception:

            continue

    result.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    return result


def process_news():

    print(
        "📰 Перевіряю новини..."
    )

    news = get_news()

    published_news = state.get(
        "published_news",
        []
    )

    published_set = set(
        published_news
    )

    count = 0

    for item in news:

        news_id = hashlib.md5(
            (
                item["title"]
                +
                item["link"]
            ).encode("utf-8")
        ).hexdigest()

        if news_id in published_set:

            continue

        message = (
            f"📰 <b>"
            f"{html.escape(item['title'])}"
            f"</b>\n\n"
            f"🔗 "
            f"{html.escape(item['link'])}"
        )

        result = send_message(
            message
        )

        if result:

            published_news.append(
                news_id
            )

            count += 1

    state["published_news"] = (
        published_news[-500:]
    )

    save_state()

    print(
        f"📰 Нових новин опубліковано: "
        f"{count}"
    )


# ============================================================
# ПОГОДА
# ============================================================

def get_weather():

    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=50.913"
        "&longitude=31.121"
        "&current=temperature_2m,"
        "relative_humidity_2m,"
        "wind_speed_10m,"
        "weather_code"
        "&timezone=Europe%2FKyiv"
    )

    try:

        response = requests.get(
            url,
            timeout=15
        )

        if response.status_code != 200:

            return None

        data = response.json()

        return data.get(
            "current",
            {}
        )

    except Exception:

        return None


def process_weather():

    weather = get_weather()

    if not weather:

        return

    temperature = weather.get(
        "temperature_2m"
    )

    humidity = weather.get(
        "relative_humidity_2m"
    )

    wind = weather.get(
        "wind_speed_10m"
    )

    message = (
        "🌤 <b>ПОГОДА — КОЗЕЛЕЦЬ</b>\n\n"
        f"🌡 Температура: {temperature}°C\n"
        f"💧 Вологість: {humidity}%\n"
        f"💨 Вітер: {wind} км/год"
    )

    send_message(
        message
    )

    print(
        "🌤 Погода оновлена."
    )


# ============================================================
# ПАНЕЛЬ
# ============================================================

def process_dashboard():

    threat = state.get(
        "threat_status",
        False
    )

    if threat:

        threat_text = (
            "🔴 НЕБЕЗПЕКА"
        )

    else:

        threat_text = (
            "🟢 СПОКІЙНО"
        )

    message = (
        "📊 <b>КОЗЕЛЕЦЬ — СТАН</b>\n\n"
        f"🚨 Повітряна обстановка: "
        f"{threat_text}\n"
        "📍 Козелець / Остер / Бобровиця\n"
        "🛰 Джерело: NEPTUN\n\n"
        "⚠️ У разі офіційної повітряної "
        "тривоги користуйтеся офіційними повідомленнями."
    )

    send_message(
        message
    )

    print(
        "📊 Панель оновлена."
    )


# ============================================================
# ПРОМО
# ============================================================

def process_promo():

    message = (
        "📢 <b>КОЗЕЛЕЦЬ ПОВІТРЯНА ТРИВОГА!</b>\n\n"
        "Тут ви можете отримувати:\n"
        "🚨 інформацію про небезпеку\n"
        "📰 місцеві новини\n"
        "🌤 погоду\n"
        "📍 важливу інформацію для громади\n\n"
        "📲 Підписуйтесь та надсилайте канал друзям!"
    )

    send_message(
        message
    )

    print(
        "📢 Промо опубліковано."
    )


# ============================================================
# ІСТОРІЯ
# ============================================================

def process_history():

    now = datetime.now(
        timezone(timedelta(hours=3))
    )

    message = (
        "📜 <b>ІСТОРІЯ КОЗЕЛЬЦЯ</b>\n\n"
        "Козелець — одне з історичних "
        "міст Чернігівщини.\n\n"
        "🏛️ Громада має багату історію, "
        "архітектурні пам'ятки та культурну спадщину.\n\n"
        f"🕒 {now.strftime('%d.%m.%Y %H:%M')}"
    )

    send_message(
        message
    )

    print(
        "📜 Історія опублікована."
    )


# ============================================================
# ГОЛОВНА ПРОГРАМА
# ============================================================

def main():

    print("=" * 60)
    print("🤖 KOZELETS ALARM BOT")
    print("=" * 60)

    print(
        datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )
    )

    print(
        "🚀 Бот запускається..."
    )

    print(
        "🛰 NEPTUN: перевірка кожні 30 секунд"
    )

    print(
        "🚨 Повідомлення NEPTUN: "
        "тільки початок та відбій"
    )

    print(
        "📰 Новини: кожні 30 хвилин"
    )

    print(
        "🌤 Погода: кожні 10 хвилин"
    )

    print(
        "📊 Панель: кожні 10 хвилин"
    )

    print(
        "📢 Промо: кожні 6 годин"
    )

    print(
        "📜 Історія: кожні 12 годин"
    )

    print("=" * 60)

    # ========================================================
    # ПЕРША ПЕРЕВІРКА ВІДРАЗУ
    # ========================================================

    print(
        "🚀 Виконую першу перевірку NEPTUN..."
    )

    process_neptun()

    print(
        "✅ Перша перевірка NEPTUN завершена."
    )

    print(
        "📰 Виконую першу перевірку новин..."
    )

    process_news()

    print(
        "🌤 Отримую погоду..."
    )

    process_weather()

    print(
        "📊 Оновлюю панель..."
    )

    process_dashboard()

    now = time.monotonic()

    last_neptun = now
    last_news = now
    last_weather = now
    last_dashboard = now
    last_promo = now
    last_history = now

    # ========================================================
    # ОСНОВНИЙ ЦИКЛ
    # ========================================================

    while True:

        now = time.monotonic()

        # ----------------------------------------------------
        # NEPTUN
        # ----------------------------------------------------

        if (
            now - last_neptun
            >= NEPTUN_CHECK_SECONDS
        ):

            process_neptun()

            last_neptun = now

        # ----------------------------------------------------
        # НОВИНИ
        # ----------------------------------------------------

        if (
            now - last_news
            >= NEWS_CHECK_SECONDS
        ):

            process_news()

            last_news = now

        # ----------------------------------------------------
        # ПОГОДА
        # ----------------------------------------------------

        if (
            now - last_weather
            >= WEATHER_CHECK_SECONDS
        ):

            process_weather()

            last_weather = now

        # ----------------------------------------------------
        # ПАНЕЛЬ
        # ----------------------------------------------------

        if (
            now - last_dashboard
            >= DASHBOARD_CHECK_SECONDS
        ):

            process_dashboard()

            last_dashboard = now

        # ----------------------------------------------------
        # ПРОМО
        # ----------------------------------------------------

        if (
            now - last_promo
            >= PROMO_CHECK_SECONDS
        ):

            process_promo()

            last_promo = now

        # ----------------------------------------------------
        # ІСТОРІЯ
        # ----------------------------------------------------

        if (
            now - last_history
            >= HISTORY_CHECK_SECONDS
        ):

            process_history()

            last_history = now

        time.sleep(1)


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    main()
