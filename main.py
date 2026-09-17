import os
import re
import json
import time
import html
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
import feedparser


# ============================================================
# KOZELETS ALARM BOT
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL = os.getenv("CHANNEL", "@Kozelets_Alarm").strip()

# API KEY НЕ ЗАПИСУЄМО В КОД.
# Він передається через GitHub Secret:
# UKRAINE_ALARM_API_KEY
UKRAINE_ALARM_API_KEY = os.getenv("UKRAINE_ALARM_API_KEY", "").strip()

TZ_NAME = "Europe/Kyiv"

# Координати Козельця
KOZELETS_LAT = 50.913
KOZELETS_LON = 31.121

STATE_FILE = Path("bot_state.json")

UA_API = "https://api.ukrainealarm.com/api/v3"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/140 Safari/537.36"
    )
}

TIMEOUT = 25


# ============================================================
# CONSOLE
# ============================================================

def log(text):
    print(text, flush=True)


# ============================================================
# STATE
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
    "pinned_message_id": None
}


def load_state():
    if not STATE_FILE.exists():
        return DEFAULT_STATE.copy()

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        state = DEFAULT_STATE.copy()

        if isinstance(data, dict):
            for key in state:
                if key in data:
                    state[key] = data[key]

        return state

    except Exception as e:
        log(f"⚠️ Не вдалося прочитати state: {e}")
        return DEFAULT_STATE.copy()


def save_state(state):
    try:
        tmp = STATE_FILE.with_suffix(".tmp")

        tmp.write_text(
            json.dumps(
                state,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        tmp.replace(STATE_FILE)

    except Exception as e:
        log(f"⚠️ Не вдалося зберегти state: {e}")


# ============================================================
# TELEGRAM
# ============================================================

def telegram(method, payload=None):
    if not BOT_TOKEN:
        log("❌ BOT_TOKEN не заданий.")
        return None

    try:
        response = requests.post(
            f"{TELEGRAM_API}/{method}",
            json=payload or {},
            timeout=TIMEOUT
        )

        if not response.ok:
            log(
                f"Telegram HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
            return None

        data = response.json()

        if not data.get("ok"):
            log(f"Telegram error: {data}")
            return None

        return data.get("result")

    except Exception as e:
        log(f"Telegram error: {e}")
        return None


def send_message(text, disable_preview=True):
    if len(text) > 4090:
        text = text[:4080] + "\n…"

    return telegram(
        "sendMessage",
        {
            "chat_id": CHANNEL,
            "text": text,
            "disable_web_page_preview": disable_preview
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
# UKRAINE ALARM
# ============================================================

def alarm_headers():
    return {
        "Authorization": UKRAINE_ALARM_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "KozeletsAlarmBot/2.0"
    }


def get_alarm_regions():
    if not UKRAINE_ALARM_API_KEY:
        log("⚠️ UKRAINE_ALARM_API_KEY не заданий.")
        return None

    try:
        r = requests.get(
            f"{UA_API}/regions",
            headers=alarm_headers(),
            timeout=TIMEOUT
        )

        if r.status_code == 401:
            log("❌ UkraineAlarm API: неправильний або недійсний API KEY.")
            return None

        if not r.ok:
            log(
                f"❌ UkraineAlarm regions HTTP "
                f"{r.status_code}: {r.text[:300]}"
            )
            return None

        return r.json()

    except Exception as e:
        log(f"❌ UkraineAlarm regions error: {e}")
        return None


def get_all_alerts():
    if not UKRAINE_ALARM_API_KEY:
        return None

    try:
        r = requests.get(
            f"{UA_API}/alerts",
            headers=alarm_headers(),
            timeout=TIMEOUT
        )

        if r.status_code == 401:
            log("❌ UkraineAlarm API: неправильний API KEY.")
            return None

        if not r.ok:
            log(
                f"❌ UkraineAlarm HTTP {r.status_code}: "
                f"{r.text[:500]}"
            )
            return None

        return r.json()

    except Exception as e:
        log(f"❌ UkraineAlarm error: {e}")
        return None


def normalize_alerts(data):
    """
    API може повертати різні структури.
    Витягуємо тільки те, що реально можемо визначити.
    """

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in (
            "alerts",
            "data",
            "regions",
            "items",
            "result"
        ):
            value = data.get(key)

            if isinstance(value, list):
                return value

    return []


def is_chernihiv_alert(item):
    if not isinstance(item, dict):
        return False

    raw = json.dumps(
        item,
        ensure_ascii=False
    ).lower()

    keywords = [
        "чернігів",
        "чернигов",
        "chernihiv",
        "chernigiv"
    ]

    return any(x in raw for x in keywords)


def get_chernihiv_alert():
    data = get_all_alerts()

    if data is None:
        return None

    alerts = normalize_alerts(data)

    for item in alerts:
        if is_chernihiv_alert(item):
            return item

    return None


def alert_is_active(alert):
    if not alert:
        return False

    if isinstance(alert, bool):
        return alert

    if not isinstance(alert, dict):
        return False

    # Найбільш типові поля
    for key in (
        "active",
        "isActive",
        "alert",
        "is_alert",
        "enabled"
    ):
        if key in alert:
            value = alert[key]

            if isinstance(value, bool):
                return value

            if str(value).lower() in (
                "true",
                "1",
                "active"
            ):
                return True

    status = str(
        alert.get("status", "")
    ).lower()

    if status in (
        "active",
        "started",
        "start",
        "alert"
    ):
        return True

    return False


def process_alarm(state):
    log("🚨 Перевіряю повітряну тривогу...")

    if not UKRAINE_ALARM_API_KEY:
        log("⚠️ UKRAINE_ALARM_API_KEY не заданий.")
        return

    alert = get_chernihiv_alert()

    if alert is None:
        log("⚠️ Стан тривоги не отримано.")
        return

    active = alert_is_active(alert)
    old_active = bool(
        state["alert"].get("active", False)
    )

    now = datetime.now().strftime(
        "%d.%m.%Y %H:%M"
    )

    if active and not old_active:
        send_message(
            "🚨 ПОВІТРЯНА ТРИВОГА\n\n"
            "📍 Чернігівська область\n"
            "⚠️ Перейдіть у безпечне місце та стежте "
            "за офіційними повідомленнями."
        )

        state["alert"]["active"] = True
        state["alert"]["last_change"] = now
        state["alert"]["last_type"] = "start"

        save_state(state)

        log("🚨 Надіслано початок тривоги.")

    elif not active and old_active:
        send_message(
            "🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
            "📍 Чернігівська область\n"
            "Можна залишати укриття лише після "
            "отримання офіційного відбою."
        )

        state["alert"]["active"] = False
        state["alert"]["last_change"] = now
        state["alert"]["last_type"] = "end"

        save_state(state)

        log("🟢 Надіслано відбій.")

    else:
        log(
            "🚨 Стан тривоги: "
            + ("АКТИВНА" if active else "немає")
        )


# ============================================================
# WEATHER
# ============================================================

def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={KOZELETS_LAT}"
        f"&longitude={KOZELETS_LON}"
        "&current=temperature_2m,relative_humidity_2m,"
        "apparent_temperature,precipitation,rain,weather_code,"
        "wind_speed_10m,wind_direction_10m"
        "&hourly=temperature_2m,precipitation_probability,"
        "precipitation,weather_code"
        "&timezone=Europe%2FKyiv"
        "&forecast_days=1"
    )

    try:
        r = requests.get(
            url,
            timeout=TIMEOUT
        )

        r.raise_for_status()
        return r.json()

    except Exception as e:
        log(f"⚠️ Weather error: {e}")
        return None


def weather_description(code):
    codes = {
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

    return codes.get(code, "невідомо")


# ============================================================
# NEWS
# ============================================================

NEWS_FEEDS = [
    (
        "Козелець",
        "https://news.google.com/rss/search?q="
        + quote("Козелець Україна")
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
    (
        "Козелеччина",
        "https://news.google.com/rss/search?q="
        + quote("Козелеччина")
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),
    (
        "ДСНС Чернігів",
        "https://news.google.com/rss/search?q="
        + quote("ДСНС Чернігівська область")
        + "&hl=uk&gl=UA&ceid=UA:uk"
    ),
    (
        "Поліція Чернігів",
        "https://news.google.com/rss/search?q="
        + quote("поліція Чернігівська область")
        + "&hl=uk&gl=UA&ceid=UA:uk"
    )
]


def clean_text(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def news_id(title, link):
    return hashlib.sha256(
        f"{title}|{link}".encode("utf-8")
    ).hexdigest()[:24]


def get_news(state):
    log("📰 Перевіряю новини...")

    seen = set(
        state.get("news_seen", [])
    )

    collected = []

    for category, url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(url)

            for entry in feed.entries[:10]:
                title = clean_text(
                    entry.get("title", "")
                )

                link = entry.get(
                    "link",
                    ""
                )

                if not title or not link:
                    continue

                nid = news_id(
                    title,
                    link
                )

                if nid in seen:
                    continue

                collected.append(
                    (
                        category,
                        title,
                        link,
                        nid
                    )
                )

        except Exception as e:
            log(
                f"⚠️ News error "
                f"{category}: {e}"
            )

    # Максимум 5 новин за один запуск
    collected = collected[:5]

    count = 0

    for category, title, link, nid in collected:
        message = (
            f"📰 {category}\n\n"
            f"🔹 {title}\n\n"
            f"🔗 {link}"
        )

        if send_message(message):
            seen.add(nid)
            count += 1

    # Не даємо state нескінченно рости
    state["news_seen"] = list(seen)[-500:]

    save_state(state)

    log(
        f"📰 Опубліковано новин: {count}"
    )


# ============================================================
# HISTORICAL POSTS
# ============================================================

HISTORY = [
    (
        "📚 КОЗЕЛЕЦЬ",
        "Козелець — історичне містечко Чернігівщини, "
        "відоме архітектурною спадщиною та пам'ятками "
        "козацької доби."
    ),
    (
        "📚 ОСТЕР",
        "Остер — одне з давніх міст Чернігівщини, "
        "розташоване на річці Остер."
    ),
    (
        "📚 БОБРОВИЦЯ",
        "Бобровиця — місто Чернігівської області "
        "з давньою історією та залізничним сполученням."
    ),
    (
        "📚 КОЗЕЛЕЧЧИНА",
        "Козелеччина поєднує історичні населені пункти, "
        "природні території та культурну спадщину "
        "Чернігівщини."
    )
]


def history_post(state):
    last = state.get("history_last")

    now = datetime.now()

    if last:
        try:
            last_dt = datetime.strptime(
                last,
                "%Y-%m-%d %H:%M:%S"
            )

            if now - last_dt < timedelta(hours=12):
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

    if send_message(message):
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
            "📚 Історичний пост опубліковано."
        )


# ============================================================
# RADIATION
# ============================================================

def radiation_info():
    """
    Не вигадуємо локальне значення радіації.
    Показуємо офіційне джерело.
    """

    return (
        "☢️ РАДІАЦІЙНИЙ ФОН\n\n"
        "ℹ️ Для коректного значення використовуються "
        "офіційні вимірювання.\n"
        "Публічне джерело:\n"
        "https://www.cgmch.pp.ua/"
    )


# ============================================================
# POWER
# ============================================================

def power_info():
    """
    Сайт Чернігівобленерго може бути недоступним
    або вимагати адресу/особовий рахунок.
    Не вигадуємо стан конкретного будинку.
    """

    return (
        "⚡ ЕЛЕКТРОПОСТАЧАННЯ\n\n"
        "ℹ️ Графік та аварійні відключення "
        "потрібно перевіряти на офіційному ресурсі "
        "Чернігівобленерго.\n\n"
        "https://chernihivoblenergo.com.ua/blackouts"
    )


# ============================================================
# DASHBOARD
# ============================================================

def dashboard_text(state):
    weather = get_weather()

    now = datetime.now().strftime(
        "%d.%m.%Y %H:%M"
    )

    active = state["alert"].get(
        "active",
        False
    )

    lines = [
        "📍 КОЗЕЛЕЦЬ | ОПЕРАТИВНА ПАНЕЛЬ",
        "",
        f"🕐 Оновлено: {now}",
        "",
        (
            "🚨 ТРИВОГА: 🔴 АКТИВНА"
            if active
            else
            "🚨 ТРИВОГА: 🟢 НЕ АКТИВНА"
        ),
        ""
    ]

    if weather:
        try:
            current = weather["current"]

            temp = current.get(
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
                "🌤 ПОГОДА",
                f"🌡 Температура: {temp} °C",
                f"🌡 Відчувається: {feels} °C",
                f"💧 Вологість: {humidity}%",
                f"💨 Вітер: {wind} км/год",
                f"☁️ Стан: {weather_description(code)}",
                ""
            ])

        except Exception:
            lines.extend([
                "🌤 ПОГОДА",
                "⚠️ Дані тимчасово недоступні.",
                ""
            ])

    lines.extend([
        radiation_info(),
        "",
        power_info(),
        "",
        "🔄 Автоматичне оновлення: кожні 5 хвилин"
    ])

    return "\n".join(lines)


def update_dashboard(state):
    text = dashboard_text(state)

    message_id = state.get(
        "pinned_message_id"
    )

    if message_id:
        result = edit_message(
            message_id,
            text
        )

        if result:
            log("📌 Панель оновлено.")
            return

        log(
            "⚠️ Не вдалося оновити стару панель. "
            "Створюю нову."
        )

    result = send_message(text)

    if result:
        new_id = result.get("message_id")

        if new_id:
            state["pinned_message_id"] = new_id
            save_state(state)

            pin_message(new_id)

            log("📌 Панель створена та закріплена.")


# ============================================================
# VALIDATION
# ============================================================

def validate_config():
    ok = True

    if not BOT_TOKEN:
        log("❌ BOT_TOKEN не заданий.")
        ok = False

    if not CHANNEL:
        log("❌ CHANNEL не заданий.")
        ok = False

    if not UKRAINE_ALARM_API_KEY:
        log(
            "⚠️ UKRAINE_ALARM_API_KEY не заданий."
        )
        log(
            "⚠️ Тривоги не працюватимуть."
        )

    return ok


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 60)
    print("🤖 KOZELETS ALARM BOT")
    print("=" * 60)
    print(
        datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )
    )
    print("=" * 60)

    if not validate_config():
        return

    state = load_state()

    process_alarm(state)

    update_dashboard(state)

    get_news(state)

    history_post(state)

    save_state(state)

    print("=" * 60)
    print("✅ ЦИКЛ ЗАВЕРШЕНО")
    print("=" * 60)


if __name__ == "__main__":
    main()
