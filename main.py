import os
import json
import math
import hashlib
import html
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
import feedparser

# ============================================================

# KOZELETS ALARM BOT

# ============================================================

print("=" * 60)
print("KOZELETS ALARM BOT")
print("=" * 60)
print(datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
print("=" * 60)

# ============================================================

# НАЛАШТУВАННЯ

# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")

STATE_FILE = Path("bot_state.json")

if not BOT_TOKEN:
raise RuntimeError("Не знайдено BOT_TOKEN")

if not CHANNEL:
raise RuntimeError("Не знайдено CHANNEL")

# ============================================================

# ІНТЕРВАЛИ

# ============================================================

NEPTUN_CHECK_SECONDS = 5 * 60
THREAT_UPDATE_SECONDS = 5 * 60

NEWS_CHECK_SECONDS = 30 * 60
NEWS_MAX_AGE_MINUTES = 30

WEATHER_CHECK_SECONDS = 10 * 60
DASHBOARD_CHECK_SECONDS = 10 * 60

PROMO_CHECK_SECONDS = 6 * 60 * 60
HISTORY_CHECK_SECONDS = 12 * 60 * 60

# ============================================================

# НАСЕЛЕНІ ПУНКТИ

# ============================================================

PLACES = {
"Козелець": (50.913, 31.121),
"Остер": (50.950, 30.883),
"Бобровиця": (50.750, 31.383),
"Кіпті": (51.050, 31.150),
"Чернігів": (51.498, 31.289),
}

THREAT_RADIUS_KM = 50

# ============================================================

# NEPTUN

# ============================================================

NEPTUN_API = "https://neptun.in.ua/api/v1/threats"
NEPTUN_URL = "https://neptun.in.ua/"

# ============================================================

# НОВИНИ

# ============================================================

NEWS_FEEDS = [
(
"Козелець",
"https://news.google.com/rss/search?q=%D0%9A%D0%BE%D0%B7%D0%B5%D0%BB%D0%B5%D1%86%D1%8C&hl=uk&gl=UA&ceid=UA:uk"
),
(
"Остер",
"https://news.google.com/rss/search?q=%D0%9E%D1%81%D1%82%D0%B5%D1%80+%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%B0&hl=uk&gl=UA&ceid=UA:uk"
),
(
"Бобровиця",
"https://news.google.com/rss/search?q=%D0%91%D0%BE%D0%B1%D1%80%D0%BE%D0%B2%D0%B8%D1%86%D1%8F&hl=uk&gl=UA&ceid=UA:uk"
),
(
"Чернігів",
"https://news.google.com/rss/search?q=%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2&hl=uk&gl=UA&ceid=UA:uk"
),
(
"Чернігівська область",
"https://news.google.com/rss/search?q=%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%B0+%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C&hl=uk&gl=UA&ceid=UA:uk"
),
]

# ============================================================

# TELEGRAM

# ============================================================

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def telegram_send(text):
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

```
    if response.status_code == 200:
        print("Telegram: повідомлення опубліковано.")
        return True

    print(
        f"Telegram помилка {response.status_code}: "
        f"{response.text[:500]}"
    )

except Exception as e:
    print(f"Помилка Telegram: {e}")

return False
```

# ============================================================

# STATE

# ============================================================

def default_state():
return {
"active_threats": {},
"last_threat_update": 0,
"last_news_check": 0,
"last_weather_check": 0,
"last_dashboard_check": 0,
"last_promo_check": 0,
"last_history_check": 0,
"published_news": [],
}

def load_state():
if not STATE_FILE.exists():
print("Файл стану не знайдено. Створюю новий.")
return default_state()

```
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
    print(f"Помилка читання bot_state.json: {e}")
    return default_state()
```

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
indent=2,
)

```
    print("Стан бота збережено.")

except Exception as e:
    print(f"Помилка збереження стану: {e}")
```

# ============================================================

# ЧАС

# ============================================================

def now_timestamp():
return datetime.now(timezone.utc).timestamp()

def kyiv_time():
return datetime.now(
timezone.utc
) + timedelta(hours=3)

def current_time_string():
return kyiv_time().strftime("%H:%M")

# ============================================================

# GEO

# ============================================================

def distance_km(lat1, lon1, lat2, lon2):
try:
radius = 6371.0

```
    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return radius * c

except Exception:
    return None
```

def nearest_place(lat, lon):
best_name = None
best_distance = None

```
for name, coords in PLACES.items():
    distance = distance_km(
        lat,
        lon,
        coords[0],
        coords[1],
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
```

# ============================================================

# ДОПОМІЖНІ ФУНКЦІЇ NEPTUN

# ============================================================

def get_value(data, *keys):
if not isinstance(data, dict):
return None

```
for key in keys:
    value = data.get(key)

    if value is not None and value != "":
        return value

return None
```

def extract_coordinates(threat):
lat = get_value(
threat,
"lat",
"latitude",
)

```
lon = get_value(
    threat,
    "lon",
    "lng",
    "longitude",
)

if lat is not None and lon is not None:
    try:
        return float(lat), float(lon)
    except Exception:
        pass

coordinates = threat.get("coordinates")

if isinstance(coordinates, dict):
    lat = get_value(
        coordinates,
        "lat",
        "latitude",
    )

    lon = get_value(
        coordinates,
        "lon",
        "lng",
        "longitude",
    )

    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except Exception:
            pass

if isinstance(coordinates, list):
    if len(coordinates) >= 2:
        try:
            return (
                float(coordinates[0]),
                float(coordinates[1]),
            )
        except Exception:
            pass

return None, None
```

def extract_heading(threat):
value = get_value(
threat,
"heading",
)

```
if value is None:
    return None

try:
    return int(round(float(value)))
except Exception:
    return str(value)
```

def make_threat_id(threat):
threat_id = get_value(
threat,
"id",
"uuid",
"threatId",
"eventId",
)

```
if threat_id:
    return str(threat_id)

raw = json.dumps(
    threat,
    ensure_ascii=False,
    sort_keys=True,
    default=str,
)

return hashlib.sha256(
    raw.encode("utf-8")
).hexdigest()
```

def threat_type_name(threat):
threat_type = get_value(
threat,
"type",
"threatType",
"category",
)

```
title = get_value(
    threat,
    "title",
    "name",
)

if threat_type:
    normalized = str(
        threat_type
    ).lower()

    if normalized in (
        "uav",
        "drone",
        "shahed",
        "бпла",
    ):
        if title:
            return f"БпЛА / {title}"

        return "БпЛА / Шахед"

    if normalized in (
        "recon",
        "reconnaissance",
    ):
        return "Розвідувальний БпЛА"

    if normalized in (
        "missile",
        "rocket",
    ):
        return "Ракета"

    if normalized == "ballistic":
        return "Балістична ракета"

    if normalized in (
        "kab",
        "bomb",
    ):
        return "Керована авіабомба"

    if normalized in (
        "mig31k",
        "mig-31k",
    ):
        return "МіГ-31К / ракетна загроза"

    return str(threat_type)

if title:
    return str(title)

return "Невідома загроза"
```

# ============================================================

# NEPTUN API

# ============================================================

def get_neptun_threats():
print("Перевіряю повітряні загрози...")

```
try:
    response = requests.get(
        NEPTUN_API,
        timeout=30,
    )

    print(
        f"API статус: {response.status_code}"
    )

    if response.status_code != 200:
        print(
            "Помилка API:",
            response.text[:500]
        )
        return []

    data = response.json()

    if isinstance(data, dict):
        threats = data.get(
            "threats",
            []
        )
    elif isinstance(data, list):
        threats = data
    else:
        threats = []

    if not isinstance(threats, list):
        threats = []

    print(
        f"Отримано загроз: {len(threats)}"
    )

    return threats

except Exception as e:
    print(
        f"Помилка отримання загроз: {e}"
    )

    return []
```

# ============================================================

# ПЕРЕВІРКА АКТИВНОСТІ

# ============================================================

def is_active_threat(threat):
status = get_value(
threat,
"status",
)

```
if status:
    status = str(
        status
    ).lower()

    if status in (
        "resolved",
        "removed",
        "closed",
        "finished",
        "inactive",
    ):
        return False

    if status in (
        "active",
        "stale",
    ):
        return True

active = get_value(
    threat,
    "active",
    "isActive",
)

if isinstance(active, bool):
    return active

return True
```

# ============================================================

# ФОРМУВАННЯ ПОВІДОМЛЕННЯ

# ============================================================

def build_threat_message(threat):
lat, lon = extract_coordinates(
threat
)

```
locality = get_value(
    threat,
    "locality",
    "settlement",
    "city",
    "town",
    "village",
)

district = get_value(
    threat,
    "district",
    "raion",
)

region = get_value(
    threat,
    "region",
    "oblast",
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

if locality:
    display_place = str(
        locality
    )
elif place:
    display_place = str(
        place
    )
elif district:
    display_place = str(
        district
    )
elif region:
    display_place = str(
        region
    )
else:
    display_place = "Чернігівщина"

threat_type = threat_type_name(
    threat
)

confidence = get_value(
    threat,
    "confidenceLevel",
    "confidence",
    "certainty",
)

if confidence is None:
    confidence = "high"

source_count = get_value(
    threat,
    "sourceCount",
)

if source_count is None:
    source_count = 1

heading = extract_heading(
    threat
)

message = []

message.append(
    "🛰 <b>ПОВІТРЯНА ЗАГРОЗА</b>"
)

message.append("")

message.append(
    f"⚠️ <b>Тип:</b> "
    f"{html.escape(str(threat_type))}"
)

message.append(
    f"📍 <b>Район:</b> "
    f"{html.escape(display_place)}"
)

if (
    distance is not None
    and not area_only
):
    message.append(
        f"📏 <b>Відстань:</b> "
        f"приблизно {distance:.1f} км"
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

message.append("")

message.append(
    f'🔗 <a href="{NEPTUN_URL}">'
    "Дані про загрозу</a>"
)

return "\n".join(message)
```

# ============================================================

# ОБРОБКА ЗАГРОЗ

# ============================================================

def process_threats(state):
threats = get_neptun_threats()

```
current = {}

for threat in threats:
    if not isinstance(
        threat,
        dict
    ):
        continue

    if not is_active_threat(
        threat
    ):
        continue

    area_only = bool(
        threat.get(
            "areaOnly",
            False
        )
    )

    lat, lon = extract_coordinates(
        threat
    )

    if (
        lat is not None
        and lon is not None
        and not area_only
    ):
        place, distance = nearest_place(
            lat,
            lon
        )

        if place is None:
            continue

        if (
            distance is not None
            and distance > THREAT_RADIUS_KM
        ):
            continue

    threat_id = make_threat_id(
        threat
    )

    current[threat_id] = threat

previous = state.get(
    "active_threats",
    {}
)

if not isinstance(
    previous,
    dict
):
    previous = {}

new_ids = [
    threat_id
    for threat_id in current
    if threat_id not in previous
]

print(
    f"Активних загроз поблизу: "
    f"{len(current)}"
)

print(
    f"Нових загроз: "
    f"{len(new_ids)}"
)

# --------------------------------------------------------
# НОВІ ЗАГРОЗИ
# --------------------------------------------------------

for threat_id in new_ids:
    message = build_threat_message(
        current[threat_id]
    )

    telegram_send(message)

# --------------------------------------------------------
# ОНОВЛЕННЯ
# --------------------------------------------------------

now = now_timestamp()

last_update = state.get(
    "last_threat_update",
    0
)

if (
    current
    and not new_ids
    and now - last_update
    >= THREAT_UPDATE_SECONDS
):
    print(
        "Оновлюю активні загрози."
    )

    for threat_id, threat in list(
        current.items()
    )[:5]:

        message = build_threat_message(
            threat
        )

        telegram_send(message)

    state["last_threat_update"] = now

# --------------------------------------------------------
# ВІДБІЙ
# --------------------------------------------------------

if previous and not current:
    telegram_send(
        "🟢 <b>ВІДБІЙ НЕБЕЗПЕКИ</b>\n\n"
        "Активних загроз поблизу "
        "контрольованих населених пунктів "
        "не виявлено."
    )

    state["last_threat_update"] = now

if not previous and current:
    state["last_threat_update"] = now

state["active_threats"] = current
```

# ============================================================

# НОВИНИ

# ============================================================

def parse_news_date(entry):
try:
if getattr(
entry,
"published_parsed",
None
):
dt = datetime(
*entry.published_parsed[:6],
tzinfo=timezone.utc,
)

```
        return dt.timestamp()

    if getattr(
        entry,
        "updated_parsed",
        None
    ):
        dt = datetime(
            *entry.updated_parsed[:6],
            tzinfo=timezone.utc,
        )

        return dt.timestamp()

except Exception:
    pass

return None
```

def make_news_id(title, link):
raw = (
str(title).strip()
+ "|"
+ str(link).strip()
)

```
return hashlib.md5(
    raw.encode("utf-8")
).hexdigest()
```

def process_news(state):
print("Перевіряю новини...")

```
now = now_timestamp()

published = state.get(
    "published_news",
    []
)

if not isinstance(
    published,
    list
):
    published = []

published_set = set(
    str(x)
    for x in published
)

new_count = 0

for source_name, feed_url in NEWS_FEEDS:
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

            if not title or not link:
                continue

            published_time = parse_news_date(
                entry
            )

            if published_time is None:
                continue

            age = (
                now
                - published_time
            )

            if age < 0:
                continue

            if (
                age
                > NEWS_MAX_AGE_MINUTES * 60
            ):
                continue

            item_id = make_news_id(
                title,
                link
            )

            if item_id in published_set:
                continue

            safe_title = html.escape(
                title
            )

            safe_source = html.escape(
                source_name
            )

            safe_link = html.escape(
                link,
                quote=True
            )

            message = (
                "📰 <b>НОВИНА</b>\n\n"
                f"📍 <b>{safe_source}</b>\n"
                f"{safe_title}\n\n"
                f'<a href="{safe_link}">'
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

                new_count += 1

    except Exception as e:
        print(
            f"Помилка новин "
            f"{source_name}: {e}"
        )

state["published_news"] = (
    published[-500:]
)

print(
    f"Нових новин опубліковано: "
    f"{new_count}"
)
```

# ============================================================

# ПОГОДА

# ============================================================

def process_weather():
print("Перевіряю погоду...")

```
latitude = PLACES[
    "Козелець"
][0]

longitude = PLACES[
    "Козелець"
][1]

url = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={latitude}"
    f"&longitude={longitude}"
    "&current=temperature_2m,"
    "apparent_temperature,"
    "relative_humidity_2m,"
    "wind_speed_10m"
    "&timezone=Europe%2FKyiv"
)

try:
    response = requests.get(
        url,
        timeout=30
    )

    if response.status_code != 200:
        print(
            f"Open-Meteo помилка: "
            f"{response.status_code}"
        )
        return

    data = response.json()

    current = data.get(
        "current",
        {}
    )

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

    message = (
        "🌤 <b>ПОГОДА — КОЗЕЛЕЦЬ</b>\n\n"
        f"🌡 Температура: "
        f"{temperature}°C\n"
        f"🥶 Відчувається: "
        f"{feels}°C\n"
        f"💧 Вологість: "
        f"{humidity}%\n"
        f"💨 Вітер: "
        f"{wind} км/год"
    )

    if telegram_send(
        message
    ):
        print(
            "Погода оновлена."
        )

except Exception as e:
    print(
        f"Помилка погоди: {e}"
    )
```

# ============================================================

# ПАНЕЛЬ

# ============================================================

def process_dashboard(state):
print("Оновлюю панель...")

```
active_count = len(
    state.get(
        "active_threats",
        {}
    )
)

if active_count:
    status = (
        "🔴 Є активна загроза"
    )
else:
    status = (
        "🟢 Активної загрози немає"
    )

message = (
    "📊 <b>СТАН КАНАЛУ</b>\n\n"
    f"🕐 Оновлено: "
    f"{current_time_string()}\n"
    f"🚨 Активних загроз: "
    f"{active_count}\n"
    f"{status}\n\n"
    "📍 Моніторинг:\n"
    "• Козелець\n"
    "• Остер\n"
    "• Бобровиця\n"
    "• Кіпті\n"
    "• Чернігів\n\n"
    "🛰 Загрози — кожні 5 хв\n"
    "📰 Новини — кожні 30 хв\n"
    "🌤 Погода — кожні 10 хв"
)

if telegram_send(
    message
):
    print(
        "Панель оновлена."
    )
```

# ============================================================

# ПРОМО

# ============================================================

def process_promo():
print("Публікую промо...")

```
message = (
    "📢 <b>КОЗЕЛЕЦЬ — ПОВІТРЯНА ТРИВОГА ТА НОВИНИ</b>\n\n"
    "У нашому каналі:\n\n"
    "🚨 повітряні загрози\n"
    "📰 місцеві новини\n"
    "🌤 погода\n"
    "📍 інформація по Козельцю та району\n\n"
    "👉 <b>Підписуйтесь та діліться "
    "каналом з близькими.</b>"
)

if telegram_send(
    message
):
    print(
        "Промо опубліковано."
    )
```

# ============================================================

# ІСТОРІЯ

# ============================================================

def process_history():
print("Публікую історичний допис...")

```
message = (
    "📜 <b>ІСТОРІЯ КОЗЕЛЬЦЯ</b>\n\n"
    "Козелець — один із відомих "
    "історичних населених пунктів "
    "Чернігівщини.\n\n"
    "🏛️ Місто має багату історію, "
    "архітектурну спадщину та цікаві "
    "місця, про які варто пам'ятати.\n\n"
    "📍 <b>Козелець — історія поруч.</b>"
)

if telegram_send(
    message
):
    print(
        "Історія опублікована."
    )
```

# ============================================================

# MAIN

# ============================================================

def main():
print("")
print("ОДНОРАЗОВИЙ ЗАПУСК")
print("Перевірка загроз — кожні 5 хвилин")
print("Оновлення активних загроз — кожні 5 хвилин")
print("Новини — тільки за останні 30 хвилин")
print("Погода — кожні 10 хвилин")
print("Панель — кожні 10 хвилин")
print("Промо — кожні 6 годин")
print("Історія — кожні 12 годин")
print("")

```
state = load_state()

now = now_timestamp()

# ========================================================
# ЗАГРОЗИ — КОЖЕН ЗАПУСК
# ========================================================

try:
    process_threats(
        state
    )
except Exception as e:
    print(
        f"Критична помилка загроз: {e}"
    )

# ========================================================
# НОВИНИ
# ========================================================

last_news = state.get(
    "last_news_check",
    0
)

if (
    now - last_news
    >= NEWS_CHECK_SECONDS
):
    try:
        process_news(
            state
        )

        state["last_news_check"] = now

    except Exception as e:
        print(
            f"Критична помилка новин: {e}"
        )
else:
    print(
        "Новини поки не час перевіряти."
    )

# ========================================================
# ПОГОДА
# ========================================================

last_weather = state.get(
    "last_weather_check",
    0
)

if (
    now - last_weather
    >= WEATHER_CHECK_SECONDS
):
    try:
        process_weather()

        state[
            "last_weather_check"
        ] = now

    except Exception as e:
        print(
            f"Критична помилка погоди: {e}"
        )
else:
    print(
        "Погоду поки не час оновлювати."
    )

# ========================================================
# ПАНЕЛЬ
# ========================================================

last_dashboard = state.get(
    "last_dashboard_check",
    0
)

if (
    now - last_dashboard
    >= DASHBOARD_CHECK_SECONDS
):
    try:
        process_dashboard(
            state
        )

        state[
            "last_dashboard_check"
        ] = now

    except Exception as e:
        print(
            f"Критична помилка панелі: {e}"
        )
else:
    print(
        "Панель поки не час оновлювати."
    )

# ========================================================
# ПРОМО
# ========================================================

last_promo = state.get(
    "last_promo_check",
    0
)

if (
    now - last_promo
    >= PROMO_CHECK_SECONDS
):
    try:
        process_promo()

        state[
            "last_promo_check"
        ] = now

    except Exception as e:
        print(
            f"Критична помилка промо: {e}"
        )
else:
    print(
        "Промо поки не час публікувати."
    )

# ========================================================
# ІСТОРІЯ
# ========================================================

last_history = state.get(
    "last_history_check",
    0
)

if (
    now - last_history
    >= HISTORY_CHECK_SECONDS
):
    try:
        process_history()

        state[
            "last_history_check"
        ] = now

    except Exception as e:
        print(
            f"Критична помилка історії: {e}"
        )
else:
    print(
        "Історію поки не час публікувати."
    )

# ========================================================
# ЗБЕРЕЖЕННЯ
# ========================================================

save_state(
    state
)

print("")
print("ЦИКЛ ЗАВЕРШЕНО")
print("Наступний запуск — приблизно через 5 хвилин.")
print("")
```

if **name** == "**main**":
main()
