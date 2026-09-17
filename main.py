import os
import re
import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import feedparser


# ============================================================
# КОНФІГУРАЦІЯ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

CHANNEL = os.getenv(
    "CHANNEL",
    "@Kozelets_Alarm"
).strip()

UKRAINE_ALARM_API_KEY = os.getenv(
    "UKRAINE_ALARM_API_KEY",
    ""
).strip()

UA_API = "https://api.ukrainealarm.com/api/v3"

TELEGRAM_API = (
    f"https://api.telegram.org/bot{BOT_TOKEN}"
)

TIMEOUT = 25

STATE_FILE = Path("bot_state.json")

# Чернігівська область
CHERNIHIV_REGION_ID = "25"

# Координати Козельця
KOZELETS_LAT = 50.913
KOZELETS_LON = 31.121

# ------------------------------------------------------------
# НОВИНИ
# ------------------------------------------------------------

# Максимальний вік новини.
#
# Бот запускається приблизно кожні 5 хвилин.
# Тому залишаємо невеликий запас у 2 хвилини.
#
# Фактично новина повинна бути приблизно не старшою 7 хвилин.
#
# Якщо хочеш абсолютно жорстко 5 хвилин:
# NEWS_MAX_AGE_MINUTES = 5
#
NEWS_MAX_AGE_MINUTES = 5

# Невеликий допуск для різниці часу між RSS та GitHub.
NEWS_FUTURE_TOLERANCE_MINUTES = 2


# ============================================================
# ЛОГ
# ============================================================

def log(text):
    print(text, flush=True)


# ============================================================
# СТАН БОТА
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
        return json.loads(
            json.dumps(DEFAULT_STATE)
        )

    try:

        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        state = json.loads(
            json.dumps(DEFAULT_STATE)
        )

        if isinstance(data, dict):

            for key in state:

                if key in data:
                    state[key] = data[key]

        return state

    except Exception as e:

        log(
            f"⚠️ Помилка читання bot_state.json: {e}"
        )

        return json.loads(
            json.dumps(DEFAULT_STATE)
        )


def save_state(state):

    try:

        temp = STATE_FILE.with_suffix(".tmp")

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
            f"⚠️ Помилка збереження state: {e}"
        )


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
                f"❌ Telegram HTTP "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )

            return None

        data = response.json()

        if not data.get("ok"):

            log(
                f"❌ Telegram API error: {data}"
            )

            return None

        return data.get("result")

    except Exception as e:

        log(
            f"❌ Telegram error: {e}"
        )

        return None


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


def edit_message(message_id, text):

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
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "KozeletsAlarmBot/1.0"
    }


def get_chernihiv_alert():

    if not UKRAINE_ALARM_API_KEY:

        log(
            "⚠️ UKRAINE_ALARM_API_KEY не заданий."
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
            f"❌ UkraineAlarm network error: {e}"
        )

        return None

    except Exception as e:

        log(
            f"❌ UkraineAlarm error: {e}"
        )

        return None


def extract_active_alerts(data):

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    active = data.get("activeAlerts")

    if isinstance(active, list):
        return active

    for key in (
        "alerts",
        "active_alerts",
        "items",
        "data"
    ):

        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


def alert_is_active(data):

    if data is None:
        return False

    active_alerts = extract_active_alerts(data)

    if len(active_alerts) > 0:
        return True

    if isinstance(data, dict):

        for key in (
            "active",
            "isActive",
            "is_active",
            "alert"
        ):

            value = data.get(key)

            if isinstance(value, bool):

                if value:
                    return True

            if str(value).lower() in (
                "true",
                "1",
                "active"
            ):

                return True

    return False


def get_alert_type(data):

    alerts = extract_active_alerts(data)

    if not alerts:

        return "Повітряна тривога"

    first = alerts[0]

    if isinstance(first, dict):

        for key in (
            "type",
            "alertType",
            "alarmType",
            "name"
        ):

            value = first.get(key)

            if value:
                return str(value)

    return "Повітряна тривога"


def process_alarm(state):

    log(
        "🚨 Перевіряю повітряну тривогу..."
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
            "⚠️ Стан Чернігівської області "
            "не отримано."
        )

        return

    active = alert_is_active(data)

    old_active = bool(
        state["alert"].get("active", False)
    )

    alert_type = get_alert_type(data)

    now = datetime.now().strftime(
        "%d.%m.%Y %H:%M:%S"
    )

    if active:

        log(
            "🚨 Стан Чернігівської області: "
            "🔴 ТРИВОГА"
        )

    else:

        log(
            "🚨 Стан Чернігівської області: "
            "🟢 НЕМАЄ ТРИВОГИ"
        )

    # --------------------------------------------------------
    # ПОЧАТОК ТРИВОГИ
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

        result = send_message(message)

        if result:

            state["alert"]["active"] = True

            state["alert"]["last_change"] = now

            state["alert"]["last_type"] = alert_type

            save_state(state)

            log(
                "🚨 Повідомлення про початок "
                "тривоги НАДІСЛАНО."
            )

    # --------------------------------------------------------
    # ВІДБІЙ
    # --------------------------------------------------------

    elif not active and old_active:

        message = (
            "🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
            "📍 Чернігівська область\n\n"
            "Офіційно отримано відбій "
            "повітряної тривоги."
        )

        result = send_message(message)

        if result:

            state["alert"]["active"] = False

            state["alert"]["last_change"] = now

            state["alert"]["last_type"] = "end"

            save_state(state)

            log(
                "🟢 Повідомлення про відбій "
                "НАДІСЛАНО."
            )

    # --------------------------------------------------------
    # СТАН НЕ ЗМІНИВСЯ
    # --------------------------------------------------------

    else:

        state["alert"]["active"] = active

        save_state(state)

        if active:

            log(
                "ℹ️ Тривога продовжується."
            )

        else:

            log(
                "ℹ️ Тривоги немає."
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
            f"⚠️ Weather error: {e}"
        )

        return None


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

        99: "гроза з градом"
    }

    return descriptions.get(
        code,
        "невідомо"
    )


# ============================================================
# НОВИНИ
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


def make_news_id(title, link):

    value = (
        f"{title}|{link}"
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:24]


def parse_news_date(entry):

    """
    Отримуємо дату новини з RSS.

    Google News зазвичай передає
    published_parsed / updated_parsed.
    """

    parsed = None

    if entry.get("published_parsed"):

        parsed = entry.get(
            "published_parsed"
        )

    elif entry.get("updated_parsed"):

        parsed = entry.get(
            "updated_parsed"
        )

    if not parsed:
        return None

    try:

        # RSS час зазвичай UTC.
        #
        # Перетворюємо його у datetime
        # з UTC.

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


def get_news(state):

    log(
        "📰 Перевіряю ТІЛЬКИ свіжі новини..."
    )

    seen = set(
        state.get(
            "news_seen",
            []
        )
    )

    collected = []

    # Поточний час UTC
    now_utc = datetime.now(
        timezone.utc
    )

    # Тільки останні 5 хвилин
    cutoff = (
        now_utc
        - timedelta(
            minutes=NEWS_MAX_AGE_MINUTES
        )
    )

    for category, url in NEWS_FEEDS:

        try:

            feed = feedparser.parse(url)

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

                # ---------------------------------------------
                # ДАТА ПУБЛІКАЦІЇ
                # ---------------------------------------------

                published_dt = parse_news_date(
                    entry
                )

                # Якщо RSS не дав дату —
                # НЕ публікуємо.
                if published_dt is None:

                    log(
                        "⏭️ Пропущено — "
                        f"немає дати: {title}"
                    )

                    continue

                # ---------------------------------------------
                # МАЙБУТНЯ ДАТА
                # ---------------------------------------------

                if published_dt > (
                    now_utc
                    + timedelta(
                        minutes=NEWS_FUTURE_TOLERANCE_MINUTES
                    )
                ):

                    log(
                        "⏭️ Пропущено — "
                        f"майбутня дата: {title}"
                    )

                    continue

                # ---------------------------------------------
                # СТАРА НОВИНА
                # ---------------------------------------------

                if published_dt < cutoff:

                    age = now_utc - published_dt

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

                # ---------------------------------------------
                # ID НОВИНИ
                # ---------------------------------------------

                news_id = make_news_id(
                    title,
                    link
                )

                # Вже публікували
                if news_id in seen:

                    log(
                        f"⏭️ Вже публікували: "
                        f"{title}"
                    )

                    continue

                # ---------------------------------------------
                # ДОДАЄМО
                # ---------------------------------------------

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

    # --------------------------------------------------------
    # СОРТУВАННЯ
    # Найновіші першими
    # --------------------------------------------------------

    collected.sort(
        key=lambda item: item[4],
        reverse=True
    )

    # --------------------------------------------------------
    # МАКСИМУМ 5 НОВИН
    # --------------------------------------------------------

    collected = collected[:5]

    published = 0

    # --------------------------------------------------------
    # ПУБЛІКАЦІЯ
    # --------------------------------------------------------

    for (
        category,
        title,
        link,
        news_id,
        published_dt
    ) in collected:

        # Переводимо час у Київ
        kyiv_time = published_dt.astimezone(
            timezone(
                timedelta(hours=3)
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
                f"📰 Опубліковано: "
                f"{title}"
            )

    # --------------------------------------------------------
    # ЗБЕРІГАЄМО ID
    # --------------------------------------------------------

    state["news_seen"] = list(
        seen
    )[-500:]

    save_state(state)

    log(
        f"📰 Опубліковано новин: "
        f"{published}"
    )


# ============================================================
# ІСТОРІЯ
# ============================================================

HISTORY = [

    (
        "📚 КОЗЕЛЕЦЬ",

        "Козелець — історичне містечко "
        "Чернігівщини, відоме архітектурною "
        "спадщиною та пам'ятками "
        "козацької доби."
    ),

    (
        "📚 ОСТЕР",

        "Остер — одне з давніх міст "
        "Чернігівщини, розташоване "
        "на річці Остер."
    ),

    (
        "📚 БОБРОВИЦЯ",

        "Бобровиця — місто Чернігівської "
        "області з давньою історією "
        "та залізничним сполученням."
    ),

    (
        "📚 КОЗЕЛЕЧЧИНА",

        "Козелеччина поєднує історичні "
        "населені пункти, природні території "
        "та культурну спадщину "
        "Чернігівщини."
    )
]


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

        save_state(state)

        log(
            "📚 Історичний пост "
            "опубліковано."
        )


# ============================================================
# РАДІАЦІЯ
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
# ЕЛЕКТРОПОСТАЧАННЯ
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

def dashboard_text(state):

    weather = get_weather()

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

    return "\n".join(lines)


def update_dashboard(state):

    text = dashboard_text(
        state
    )

    message_id = state.get(
        "pinned_message_id"
    )

    # --------------------------------------------------------
    # ОНОВЛЮЄМО СТАРУ ПАНЕЛЬ
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # СТВОРЮЄМО НОВУ
    # --------------------------------------------------------

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
# ПЕРЕВІРКА КОНФІГУРАЦІЇ
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

    print("=" * 60)

    print(
        "🤖 KOZELETS ALARM BOT"
    )

    print("=" * 60)

    print(
        datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )
    )

    print("=" * 60)

    if not validate_config():

        log(
            "❌ Конфігурація неповна."
        )

        return

    state = load_state()

    # --------------------------------------------------------
    # 1. ПОВІТРЯНА ТРИВОГА
    # --------------------------------------------------------

    process_alarm(
        state
    )

    # --------------------------------------------------------
    # 2. ОПЕРАТИВНА ПАНЕЛЬ
    # --------------------------------------------------------

    update_dashboard(
        state
    )

    # --------------------------------------------------------
    # 3. НОВИНИ
    # --------------------------------------------------------

    get_news(
        state
    )

    # --------------------------------------------------------
    # 4. ІСТОРІЯ
    # --------------------------------------------------------

    history_post(
        state
    )

    # --------------------------------------------------------
    # 5. ЗБЕРЕЖЕННЯ
    # --------------------------------------------------------

    save_state(
        state
    )

    print("=" * 60)

    print(
        "✅ ЦИКЛ ЗАВЕРШЕНО"
    )

    print("=" * 60)


if __name__ == "__main__":

    main()
