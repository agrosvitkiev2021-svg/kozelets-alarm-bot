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

# Історія — раз на 12 годин
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
        "q=%D0%9E%D1%81%D1%82%D0%B5%D1%80+%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%B0"
        "&hl=uk&gl=UA&ceid=UA:uk"
    ),
    (
        "Чернігівська область",
        "https://news.google.com/rss/search?"
        "q=%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%B0+%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C"
        "&hl=uk&gl=UA&ceid=UA:uk"
    ),
]


# ============================================================
# TELEGRAM API
# ============================================================

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram_send(text):
    """
    Відправка повідомлення в Telegram.
    """

    try:
        response = requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            data={
                "chat_id": CHANNEL,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
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
# ============================================================
# ОФІЦІЙНА ПОВІТРЯНА ТРИВОГА
# ЧЕРНІГІВСЬКИЙ РАЙОН
# ============================================================
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

    # --------------------------------------------------------
    # Варіант 1 — список
    # --------------------------------------------------------

    if isinstance(data, list):

        if len(data) == 0:
            return False

        item = data[0]

    # --------------------------------------------------------
    # Варіант 2 — dict
    # --------------------------------------------------------

    elif isinstance(data, dict):

        # Якщо API повернув об'єкт регіону
        if (
            "activeAlerts" in data
            or "regionName" in data
            or "regionId" in data
        ):

            item = data

        # Якщо дані знаходяться у states
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

    # --------------------------------------------------------
    # Визначаємо activeAlerts
    # --------------------------------------------------------

    active_alerts = item.get(
        "activeAlerts"
    )

    # Якщо activeAlerts — список
    if isinstance(
        active_alerts,
        list
    ):

        active = len(active_alerts) > 0

    # Якщо activeAlerts — dict
    elif isinstance(
        active_alerts,
        dict
    ):

        active = len(active_alerts) > 0

    # Якщо activeAlerts — bool
    elif isinstance(
        active_alerts,
        bool
    ):

        active = active_alerts

    else:

        # Додатковий варіант
        active_value = get_value(
            item,
            "active",
            "isActive"
        )

        if isinstance(
            active_value,
            bool
        ):

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

    # --------------------------------------------------------
    # API не відповів
    # --------------------------------------------------------

    if current_alert is None:

        print(
            "⚠️ Стан тривоги не змінюю, "
            "оскільки API не відповів."
        )

        return

    previous_alert = state.get(
        "district_alert_active"
    )

    initialized = state.get(
        "district_alert_initialized",
        False
    )

    # --------------------------------------------------------
    # ПЕРШЕ УСПІШНЕ ОПИТУВАННЯ
    # --------------------------------------------------------

    if not initialized:

        state[
            "district_alert_active"
        ] = current_alert

        state[
            "district_alert_initialized"
        ] = True

        print(
            "ℹ️ Початковий стан "
            f"{AIR_REGION_NAME} записано: "
            f"{current_alert}"
        )

        # Якщо бот запускається вперше саме під час
        # активної тривоги — повідомляємо канал.
        if current_alert:

            telegram_send(
                "🔴 <b>ПОВІТРЯНА ТРИВОГА</b>\n\n"
                f"📍 <b>{html.escape(AIR_REGION_NAME)}</b>\n\n"
                "⚠️ У районі оголошено "
                "повітряну тривогу.\n\n"
                f"🕐 Час: {current_time_string()}"
            )

        return

    # --------------------------------------------------------
    # ПОЧАТОК ТРИВОГИ
    # --------------------------------------------------------

    if (
        current_alert is True
        and previous_alert is not True
    ):

        print(
            "🔴 НОВА ТРИВОГА "
            f"в {AIR_REGION_NAME}"
        )

        message = (
            "🔴 <b>ПОВІТРЯНА ТРИВОГА</b>\n\n"
            f"📍 <b>{html.escape(AIR_REGION_NAME)}</b>\n\n"
            "⚠️ У районі оголошено "
            "повітряну тривогу.\n\n"
            f"🕐 Час початку: "
            f"{current_time_string()}\n\n"
            "🚨 Перейдіть у безпечне місце "
            "та дотримуйтесь правил безпеки."
        )

        if telegram_send(message):

            state[
                "district_alert_active"
            ] = True

    # --------------------------------------------------------
    # ВІДБІЙ ТРИВОГИ
    # --------------------------------------------------------

    elif (
        current_alert is False
        and previous_alert is True
    ):

        print(
            "🟢 ВІДБІЙ ТРИВОГИ "
            f"в {AIR_REGION_NAME}"
        )

        message = (
            "🟢 <b>ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ</b>\n\n"
            f"📍 <b>{html.escape(AIR_REGION_NAME)}</b>\n\n"
            "✅ У районі оголошено відбій "
            "повітряної тривоги.\n\n"
            f"🕐 Час відбою: "
            f"{current_time_string()}"
        )

        if telegram_send(message):

            state[
                "district_alert_active"
            ] = False

    # --------------------------------------------------------
    # СТАН НЕ ЗМІНИВСЯ
    # --------------------------------------------------------

    else:

        state[
            "district_alert_active"
        ] = current_alert

        print(
            "ℹ️ Стан тривоги не змінився."
        )


# ============================================================
# NEPTUN
# ============================================================

def extract_coordinates(threat):

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
        and lon is not None
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
            and lon is not None
        ):

            try:

                return (
                    float(lat),
                    float(lon)
                )

            except Exception:
                pass

    if (
        isinstance(
            coordinates,
            list
        )
        and len(coordinates) >= 2
    ):

        try:

            return (
                float(coordinates[0]),
                float(coordinates[1])
            )

        except Exception:
            pass

    return None, None


def extract_heading(threat):

    value = get_value(
        threat,
        "heading"
    )

    if value is None:
        return None

    try:

        return int(
            round(
                float(value)
            )
        )

    except Exception:

        return str(value)


def make_threat_id(threat):

    threat_id = get_value(
        threat,
        "id",
        "uuid",
        "threatId",
        "eventId"
    )

    if threat_id:

        return str(threat_id)

    raw = json.dumps(
        threat,
        ensure_ascii=False,
        sort_keys=True,
        default=str
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def threat_type_name(threat):

    threat_type = get_value(
        threat,
        "type",
        "threatType",
        "category"
    )

    title = get_value(
        threat,
        "title",
        "name"
    )

    if threat_type:

        normalized = str(
            threat_type
        ).lower()

        if normalized in (
            "uav",
            "drone",
            "shahed",
            "бпла"
        ):

            return (
                f"БпЛА / {title}"
                if title
                else
                "БпЛА / Шахед"
            )

        if normalized in (
            "recon",
            "reconnaissance"
        ):

            return "Розвідувальний БпЛА"

        if normalized in (
            "missile",
            "rocket"
        ):

            return "Ракета"

        if normalized == "ballistic":

            return "Балістична ракета"

        if normalized in (
            "kab",
            "bomb"
        ):

            return "Керована авіабомба"

        if normalized in (
            "mig31k",
            "mig-31k"
        ):

            return "МіГ-31К / ракетна загроза"

        return str(threat_type)

    return (
        str(title)
        if title
        else
        "Невідома загроза"
    )


def get_neptun_threats():

    print(
        "🛰 Перевіряю повітряні загрози NEPTUN..."
    )

    try:

        response = requests.get(
            NEPTUN_API,
            timeout=30
        )

        if response.status_code != 200:

            print(
                f"❌ NEPTUN HTTP "
                f"{response.status_code}"
            )

            return []

        data = response.json()

        threats = (
            data.get(
                "threats",
                []
            )
            if isinstance(
                data,
                dict
            )
            else data
        )

        if not isinstance(
            threats,
            list
        ):

            return []

        print(
            f"✅ NEPTUN: "
            f"отримано {len(threats)} загроз."
        )

        return threats

    except Exception as e:

        print(
            f"❌ Помилка отримання "
            f"NEPTUN: {e}"
        )

        return []


def is_active_threat(threat):

    status = get_value(
        threat,
        "status"
    )

    if status:

        status = str(
            status
        ).lower()

        if status in (
            "resolved",
            "removed",
            "closed",
            "finished",
            "inactive"
        ):

            return False

        if status in (
            "active",
            "stale"
        ):

            return True

    active = get_value(
        threat,
        "active",
        "isActive"
    )

    return (
        active
        if isinstance(
            active,
            bool
        )
        else True
    )


def build_threat_message(threat):

    lat, lon = extract_coordinates(
        threat
    )

    area_only = bool(
        threat.get(
            "areaOnly",
            False
        )
    )

    place = None
    distance = None

    if (
        lat is not None
        and lon is not None
        and not area_only
    ):

        place, distance = nearest_place(
            lat,
            lon
        )

    display_place = (
        place
        or
        "Козелеччина / поблизу"
    )

    threat_type = threat_type_name(
        threat
    )

    confidence = (
        get_value(
            threat,
            "confidenceLevel",
            "confidence",
            "certainty"
        )
        or
        "high"
    )

    source_count = (
        get_value(
            threat,
            "sourceCount"
        )
        or
        1
    )

    heading = extract_heading(
        threat
    )

    message = [
        "🛰 <b>ПОВІТРЯНА ЗАГРОЗА ПОБЛИЗУ</b>\n",
        (
            f"⚠️ <b>Тип:</b> "
            f"{html.escape(str(threat_type))}"
        ),
        (
            f"📍 <b>Напрямок/Район:</b> "
            f"{html.escape(str(display_place))}"
        ),
    ]

    if (
        distance is not None
        and not area_only
    ):

        message.append(
            f"📏 <b>Відстань до населеного пункту:</b> "
            f"~{distance:.1f} км"
        )

    message.append(
        f"🎯 <b>Достовірність:</b> "
        f"{html.escape(str(confidence))}"
    )

    message.append(
        f"📡 <b>Джерел:</b> "
        f"{html.escape(str(source_count))}"
    )

    if (
        heading is not None
        and not area_only
    ):

        message.append(
            f"🧭 <b>Курс:</b> "
            f"{html.escape(str(heading))}°"
        )

    message.append(
        f'\n🔗 <a href="{NEPTUN_URL}">'
        "Карта Neptun</a>"
    )

    return "\n".join(
        message
    )


def process_threats(state):

    threats = get_neptun_threats()

    current = {}

    for threat in threats:

        if (
            not isinstance(
                threat,
                dict
            )
            or not is_active_threat(
                threat
            )
        ):

            continue

        area_only = bool(
            threat.get(
                "areaOnly",
                False
            )
        )

        if area_only:
            continue

        lat, lon = extract_coordinates(
            threat
        )

        if (
            lat is None
            or lon is None
        ):

            continue

        place, distance = nearest_place(
            lat,
            lon
        )

        if (
            place is None
            or distance is None
            or distance > THREAT_RADIUS_KM
        ):

            continue

        threat_id = make_threat_id(
            threat
        )

        current[
            threat_id
        ] = threat

    previous = state.get(
        "active_threats",
        {}
    )

    if not isinstance(
        previous,
        dict
    ):

        previous = {}

    # --------------------------------------------------------
    # НОВІ ЗАГРОЗИ
    # --------------------------------------------------------

    new_ids = [
        threat_id
        for threat_id in current
        if threat_id not in previous
    ]

    for threat_id in new_ids:

        telegram_send(
            build_threat_message(
                current[threat_id]
            )
        )

    now = now_timestamp()

    last_update = state.get(
        "last_threat_update",
        0
    )

    # --------------------------------------------------------
    # ОНОВЛЕННЯ АКТИВНОЇ ЗАГРОЗИ
    # --------------------------------------------------------

    if (
        current
        and not new_ids
        and (
            now - last_update
            >= THREAT_UPDATE_SECONDS
        )
    ):

        for (
            threat_id,
            threat
        ) in list(
            current.items()
        )[:5]:

            telegram_send(
                build_threat_message(
                    threat
                )
            )

        state[
            "last_threat_update"
        ] = now

    # --------------------------------------------------------
    # ВІДБІЙ NEPTUN
    # --------------------------------------------------------

    if (
        previous
        and not current
    ):

        telegram_send(
            "🟢 <b>ВІДБІЙ ПОБЛИЗУ</b>\n\n"
            "У радіусі 25 км активних "
            "цілей не виявлено."
        )

        state[
            "last_threat_update"
        ] = now

    # --------------------------------------------------------
    # ЗАПИС СТАНУ
    # --------------------------------------------------------

    if (
        not previous
        and current
    ):

        state[
            "last_threat_update"
        ] = now

    state[
        "active_threats"
    ] = current


# ============================================================
# НОВИНИ
# ============================================================

def process_news(state):

    print(
        "📰 Обробка новин..."
    )

    now = now_timestamp()

    published = state.get(
        "published_news",
        []
    )

    published_set = set(
        str(x)
        for x in published
    )

    for (
        source_name,
        feed_url
    ) in NEWS_FEEDS:

        try:

            feed = feedparser.parse(
                feed_url
            )

            for entry in feed.entries:

                title = getattr(
                    entry,
                    "title",
                    ""
                ).strip()

                link = getattr(
                    entry,
                    "link",
                    ""
                ).strip()

                if (
                    not title
                    or not link
                ):

                    continue

                published_time = None

                if getattr(
                    entry,
                    "published_parsed",
                    None
                ):

                    published_time = (
                        datetime(
                            *entry.published_parsed[:6],
                            tzinfo=timezone.utc
                        ).timestamp()
                    )

                # Якщо немає часу публікації —
                # пропускаємо
                if published_time is None:

                    continue

                # Тільки новини не старші 30 хв
                age = (
                    now
                    - published_time
                )

                if (
                    age < 0
                    or
                    age >
                    NEWS_MAX_AGE_MINUTES * 60
                ):

                    continue

                item_id = hashlib.md5(
                    (
                        title
                        + "|"
                        + link
                    ).encode(
                        "utf-8"
                    )
                ).hexdigest()

                if item_id in published_set:
                    continue

                message = (
                    "📰 <b>НОВИНА</b>\n\n"
                    f"📍 <b>{html.escape(source_name)}</b>\n"
                    f"{html.escape(title)}\n\n"
                    f'<a href="{html.escape(link, quote=True)}">'
                    "🔗 Читати новину</a>"
                )

                if telegram_send(
                    message
                ):

                    published.append(
                        item_id
                    )

                    published_set.add(
                        item_id
                    )

        except Exception as e:

            print(
                f"❌ Помилка RSS "
                f"{source_name}: {e}"
            )

    # Зберігаємо максимум 500 ID
    state[
        "published_news"
    ] = published[-500:]


# ============================================================
# ПОГОДА
# ============================================================

def process_weather():

    print(
        "🌤 Публікація погоди..."
    )

    lat, lon = PLACES[
        "Козелець"
    ]

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}"
        f"&longitude={lon}"
        "&current="
        "temperature_2m,"
        "apparent_temperature,"
        "relative_humidity_2m,"
        "wind_speed_10m"
        "&daily=sunrise,sunset"
        "&timezone=Europe%2FKyiv"
    )

    try:

        response = requests.get(
            url,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        current = data.get(
            "current",
            {}
        )

        daily = data.get(
            "daily",
            {}
        )

        temp = round(
            float(
                current.get(
                    "temperature_2m",
                    0
                )
            ),
            1
        )

        feels = round(
            float(
                current.get(
                    "apparent_temperature",
                    0
                )
            ),
            1
        )

        humidity = current.get(
            "relative_humidity_2m"
        )

        wind = round(
            float(
                current.get(
                    "wind_speed_10m",
                    0
                )
            ),
            1
        )

        sunrise_str = (
            daily.get(
                "sunrise",
                [""]
            )[0]
        )

        sunset_str = (
            daily.get(
                "sunset",
                [""]
            )[0]
        )

        if (
            sunrise_str
            and sunset_str
        ):

            sunrise_dt = datetime.fromisoformat(
                sunrise_str
            )

            sunset_dt = datetime.fromisoformat(
                sunset_str
            )

            sunrise = sunrise_dt.strftime(
                "%H:%M"
            )

            sunset = sunset_dt.strftime(
                "%H:%M"
            )

            day_duration = (
                sunset_dt
                - sunrise_dt
            )

            total_minutes = (
                int(
                    day_duration.total_seconds()
                    // 60
                )
            )

            hours = total_minutes // 60

            minutes = (
                total_minutes
                % 60
            )

            day_len_str = (
                f"{hours} год "
                f"{minutes} хв"
            )

        else:

            sunrise = "—"
            sunset = "—"
            day_len_str = "—"

        # УВАГА:
        # Це не вимірювання радіації.
        # Значення прибране з автоматичної
        # генерації, щоб не публікувати
        # вигаданий показник.

        msg = (
            "🌤 <b>ПОГОДА — КОЗЕЛЕЦЬ</b>\n\n"
            f"🌡 Температура: {temp}°C\n"
            f"🥶 Відчувається: {feels}°C\n"
            f"💧 Вологість: {humidity}%\n"
            f"💨 Вітер: {wind} км/год\n\n"
            f"🌅 Схід: {sunrise}\n"
            f"🌇 Захід: {sunset}\n"
            f"⏳ Тривалість дня: {day_len_str}\n\n"
            f"🕐 Оновлено: {current_time_string()}"
        )

        telegram_send(
            msg
        )

    except Exception as e:

        print(
            f"❌ Помилка погоди: {e}"
        )


# ============================================================
# ПРОМО
# ============================================================

def process_promo():

    print(
        "📢 Публікація промо..."
    )

    msg = (
        "📢 <b>КОЗЕЛЕЦЬ — "
        "ПОВІТРЯНА ТРИВОГА ТА НОВИНИ</b>\n\n"
        "🚨 загрози поруч\n"
        "📰 новини\n"
        "🌤 погода\n\n"
        "👉 <b>Підписуйтесь та "
        "діліться з близькими.</b>"
    )

    telegram_send(
        msg
    )


# ============================================================
# ІСТОРІЯ
# ============================================================

def process_history():

    print(
        "📜 Публікація історії..."
    )

    msg = (
        "📜 <b>ІСТОРІЯ КОЗЕЛЬЦЯ</b>\n\n"
        "Козелець — один із відомих "
        "історичних населених пунктів "
        "Чернігівщини.\n\n"
        "📍 <b>Козелець — історія поруч.</b>"
    )

    telegram_send(
        msg
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n🚀 Запуск основного циклу..."
    )

    state = load_state()

    now = now_timestamp()

    # ========================================================
    # 1. ОФІЦІЙНА ТРИВОГА ЧЕРНІГІВСЬКОГО РАЙОНУ
    # ========================================================

    try:

        process_district_alert(
            state
        )

    except Exception as e:

        print(
            f"❌ Помилка офіційної "
            f"тривоги: {e}"
        )

    # ========================================================
    # 2. NEPTUN
    # ========================================================

    try:

        process_threats(
            state
        )

    except Exception as e:

        print(
            f"❌ Помилка NEPTUN: {e}"
        )

    # ========================================================
    # 3. НОВИНИ — 30 ХВ
    # ========================================================

    if (
        now
        - state.get(
            "last_news_check",
            0
        )
        >= NEWS_CHECK_SECONDS
    ):

        try:

            process_news(
                state
            )

            state[
                "last_news_check"
            ] = now

        except Exception as e:

            print(
                f"❌ Помилка новин: {e}"
            )

    else:

        passed = int(
            now
            - state.get(
                "last_news_check",
                0
            )
        )

        print(
            "📰 Новини пропущено: "
            f"{passed}/{NEWS_CHECK_SECONDS} сек."
        )

    # ========================================================
    # 4. ПОГОДА — 4 ГОДИНИ
    # ========================================================

    if (
        now
        - state.get(
            "last_weather_check",
            0
        )
        >= WEATHER_CHECK_SECONDS
    ):

        try:

            process_weather()

            state[
                "last_weather_check"
            ] = now

        except Exception as e:

            print(
                f"❌ Помилка погоди: {e}"
            )

    else:

        passed = int(
            now
            - state.get(
                "last_weather_check",
                0
            )
        )

        print(
            "🌤 Погода пропущена: "
            f"{passed}/{WEATHER_CHECK_SECONDS} сек."
        )

    # ========================================================
    # 5. ПРОМО — 6 ГОДИН
    # ========================================================

    if (
        now
        - state.get(
            "last_promo_check",
            0
        )
        >= PROMO_CHECK_SECONDS
    ):

        try:

            process_promo()

            state[
                "last_promo_check"
            ] = now

        except Exception as e:

            print(
                f"❌ Помилка промо: {e}"
            )

    # ========================================================
    # 6. ІСТОРІЯ — 12 ГОДИН
    # ========================================================

    if (
        now
        - state.get(
            "last_history_check",
            0
        )
        >= HISTORY_CHECK_SECONDS
    ):

        try:

            process_history()

            state[
                "last_history_check"
            ] = now

        except Exception as e:

            print(
                f"❌ Помилка історії: {e}"
            )

    # ========================================================
    # ЗБЕРЕЖЕННЯ СТАНУ
    # ========================================================

    save_state(
        state
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "✅ ЦИКЛ ЗАВЕРШЕНО"
    )

    print(
        "=" * 70
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
