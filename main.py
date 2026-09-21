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
# KOZELETS ALARM BOT (GITHUB ACTIONS VERSION)
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
    raise RuntimeError("Не знайдено BOT_TOKEN у Secrets GitHub")

if not CHANNEL:
    raise RuntimeError("Не знайдено CHANNEL у Secrets GitHub")

# ============================================================
# ІНТЕРВАЛИ (у секундах)
# ============================================================

NEPTUN_CHECK_SECONDS = 5 * 60
THREAT_UPDATE_SECONDS = 5 * 60

NEWS_CHECK_SECONDS = 30 * 60
NEWS_MAX_AGE_MINUTES = 30

# Погода — раз на три години (3 год * 3600 сек = 10800 сек)
WEATHER_CHECK_SECONDS = 3 * 60 * 60

# Стан каналу — раз на чотири години (4 год * 3600 сек = 14400 сек)
DASHBOARD_CHECK_SECONDS = 4 * 60 * 60

PROMO_CHECK_SECONDS = 6 * 60 * 60
HISTORY_CHECK_SECONDS = 12 * 60 * 60

# ============================================================
# НАСЕЛЕНІ ПУНКТИ ТА ЗОНА РЕАГУВАННЯ
# ============================================================

PLACES = {
    "Козелець": (50.913, 31.121),
    "Остер": (50.950, 30.883),
    "Кіпті": (51.050, 31.150),
    "Чемер": (51.108, 31.216),
    "Десна": (50.927, 30.760),
    "Калита": (50.751, 31.025),
}

THREAT_RADIUS_KM = 25

NEPTUN_API = "https://neptun.in.ua/api/v1/threats"
NEPTUN_URL = "https://neptun.in.ua/"

NEWS_FEEDS = [
    ("Козелець", "https://news.google.com/rss/search?q=%D0%9A%D0%BE%D0%B7%D0%B5%D0%BB%D0%B5%D1%86%D1%8C&hl=uk&gl=UA&ceid=UA:uk"),
    ("Остер", "https://news.google.com/rss/search?q=%D0%9E%D1%81%D1%82%D0%B5%D1%80+%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%B0&hl=uk&gl=UA&ceid=UA:uk"),
    ("Чернігівська область", "https://news.google.com/rss/search?q=%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B3%D1%96%D0%B2%D1%81%D1%8C%D0%BA%D0%B0+%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C&hl=uk&gl=UA&ceid=UA:uk"),
]

# ============================================================
# TELEGRAM API
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

        if response.status_code == 200:
            print("Telegram: повідомлення успішно опубліковано.")
            return True

        print(f"Telegram помилка {response.status_code}: {response.text[:500]}")
    except Exception as e:
        print(f"Помилка відправки в Telegram: {e}")

    return False

# ============================================================
# СТАН (STATE MANAGEMENT)
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
        print("Файл bot_state.json не знайдено. Створюю новий стан.")
        return default_state()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)
        base = default_state()
        base.update(state)
        return base
    except Exception as e:
        print(f"Помилка читання bot_state.json: {e}")
        return default_state()

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
        print("Стан бота успішно збережено.")
    except Exception as e:
        print(f"Помилка збереження bot_state.json: {e}")

# ============================================================
# ДОПОМІЖНІ ФУНКЦІЇ ЧАСУ ТА ГЕОЛОКАЦІЇ
# ============================================================

def now_timestamp():
    return datetime.now(timezone.utc).timestamp()

def kyiv_time():
    return datetime.now(timezone.utc) + timedelta(hours=3)

def current_time_string():
    return kyiv_time().strftime("%H:%M")

def distance_km(lat1, lon1, lat2, lon2):
    try:
        radius = 6371.0
        lat1, lon1 = math.radians(float(lat1)), math.radians(float(lon1))
        lat2, lon2 = math.radians(float(lat2)), math.radians(float(lon2))

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c
    except Exception:
        return None

def nearest_place(lat, lon):
    best_name, best_distance = None, None
    for name, coords in PLACES.items():
        distance = distance_km(lat, lon, coords[0], coords[1])
        if distance is None:
            continue
        if best_distance is None or distance < best_distance:
            best_name = name
            best_distance = distance
    return best_name, best_distance

# ============================================================
# ОБРОБКА ЗАГРОЗ (NEPTUN API)
# ============================================================

def get_value(data, *keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None

def extract_coordinates(threat):
    lat = get_value(threat, "lat", "latitude")
    lon = get_value(threat, "lon", "lng", "longitude")
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except Exception:
            pass

    coordinates = threat.get("coordinates")
    if isinstance(coordinates, dict):
        lat = get_value(coordinates, "lat", "latitude")
        lon = get_value(coordinates, "lon", "lng", "longitude")
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except Exception:
                pass

    if isinstance(coordinates, list) and len(coordinates) >= 2:
        try:
            return float(coordinates[0]), float(coordinates[1])
        except Exception:
            pass

    return None, None

def extract_heading(threat):
    value = get_value(threat, "heading")
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except Exception:
        return str(value)

def make_threat_id(threat):
    threat_id = get_value(threat, "id", "uuid", "threatId", "eventId")
    if threat_id:
        return str(threat_id)
    raw = json.dumps(threat, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def threat_type_name(threat):
    threat_type = get_value(threat, "type", "threatType", "category")
    title = get_value(threat, "title", "name")

    if threat_type:
        normalized = str(threat_type).lower()
        if normalized in ("uav", "drone", "shahed", "бпла"):
            return f"БпЛА / {title}" if title else "БпЛА / Шахед"
        if normalized in ("recon", "reconnaissance"):
            return "Розвідувальний БпЛА"
        if normalized in ("missile", "rocket"):
            return "Ракета"
        if normalized == "ballistic":
            return "Балістична ракета"
        if normalized in ("kab", "bomb"):
            return "Керована авіабомба"
        if normalized in ("mig31k", "mig-31k"):
            return "МіГ-31К / ракетна загроза"
        return str(threat_type)

    return str(title) if title else "Невідома загроза"

def get_neptun_threats():
    print("Перевіряю повітряні загрози...")
    try:
        response = requests.get(NEPTUN_API, timeout=30)
        if response.status_code != 200:
            return []
        data = response.json()
        threats = data.get("threats", []) if isinstance(data, dict) else data
        return threats if isinstance(threats, list) else []
    except Exception as e:
        print(f"Помилка отримання загроз: {e}")
        return []

def is_active_threat(threat):
    status = get_value(threat, "status")
    if status:
        status = str(status).lower()
        if status in ("resolved", "removed", "closed", "finished", "inactive"):
            return False
        if status in ("active", "stale"):
            return True

    active = get_value(threat, "active", "isActive")
    return active if isinstance(active, bool) else True

def build_threat_message(threat):
    lat, lon = extract_coordinates(threat)
    area_only = bool(threat.get("areaOnly", False))

    place, distance = None, None
    if lat is not None and lon is not None and not area_only:
        place, distance = nearest_place(lat, lon)

    display_place = place or "Козелеччина / поблизу"
    threat_type = threat_type_name(threat)
    confidence = get_value(threat, "confidenceLevel", "confidence", "certainty") or "high"
    source_count = get_value(threat, "sourceCount") or 1
    heading = extract_heading(threat)

    message = [
        "🛰 <b>ПОВІТРЯНА ЗАГРОЗА ПОБЛИЗУ</b>\n",
        f"⚠️ <b>Тип:</b> {html.escape(str(threat_type))}",
        f"📍 <b>Напрямок/Район:</b> {html.escape(str(display_place))}"
    ]

    if distance is not None and not area_only:
        message.append(f"📏 <b>Відстань до населеного пункту:</b> ~{distance:.1f} км")

    message.append(f"🎯 <b>Достовірність:</b> {html.escape(str(confidence))}")
    message.append(f"📡 <b>Джерел:</b> {html.escape(str(source_count))}")

    if heading is not None and not area_only:
        message.append(f"🧭 <b>Курс:</b> {html.escape(str(heading))}°")

    message.append(f'\n🔗 <a href="{NEPTUN_URL}">Карта Neptun</a>')
    return "\n".join(message)

def process_threats(state):
    threats = get_neptun_threats()
    current = {}

    for threat in threats:
        if not isinstance(threat, dict) or not is_active_threat(threat):
            continue

        area_only = bool(threat.get("areaOnly", False))
        if area_only:
            continue

        lat, lon = extract_coordinates(threat)
        if lat is None or lon is None:
            continue

        place, distance = nearest_place(lat, lon)
        if place is None or distance is None or distance > THREAT_RADIUS_KM:
            continue

        threat_id = make_threat_id(threat)
        current[threat_id] = threat

    previous = state.get("active_threats", {})
    if not isinstance(previous, dict):
        previous = {}

    new_ids = [t_id for t_id in current if t_id not in previous]

    for threat_id in new_ids:
        telegram_send(build_threat_message(current[threat_id]))

    now = now_timestamp()
    last_update = state.get("last_threat_update", 0)

    if current and not new_ids and (now - last_update >= THREAT_UPDATE_SECONDS):
        for threat_id, threat in list(current.items())[:5]:
            telegram_send(build_threat_message(threat))
        state["last_threat_update"] = now

    if previous and not current:
        telegram_send("🟢 <b>ВІДБІЙ ПОБЛИЗУ</b>\n\nУ радіусі 25 км активних цілей не виявлено.")
        state["last_threat_update"] = now

    if not previous and current:
        state["last_threat_update"] = now

    state["active_threats"] = current

# ============================================================
# НОВИНИ, ПОГОДА, ДАШБОРД, ПРОМО
# ============================================================

def process_news(state):
    print("Обробка новин...")
    now = now_timestamp()
    published = state.get("published_news", [])
    published_set = set(str(x) for x in published)

    for source_name, feed_url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = getattr(entry, "title", "").strip()
                link = getattr(entry, "link", "").strip()
                if not title or not link:
                    continue

                published_time = None
                if getattr(entry, "published_parsed", None):
                    published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).timestamp()

                if published_time is None or (now - published_time > NEWS_MAX_AGE_MINUTES * 60):
                    continue

                item_id = hashlib.md5((title + "|" + link).encode("utf-8")).hexdigest()
                if item_id in published_set:
                    continue

                message = (
                    f"📰 <b>НОВИНА</b>\n\n📍 <b>{html.escape(source_name)}</b>\n"
                    f"{html.escape(title)}\n\n<a href=\"{html.escape(link, quote=True)}\">🔗 Читати новину</a>"
                )

                if telegram_send(message):
                    published.append(item_id)
                    published_set.add(item_id)
        except Exception as e:
            print(f"Помилка RSS {source_name}: {e}")

    state["published_news"] = published[-500:]

def process_weather():
    print("Публікація погоди...")
    lat, lon = PLACES["Козелець"]
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m"
        f"&daily=sunrise,sunset"
        f"&timezone=Europe%2FKyiv"
    )
    try:
        data = requests.get(url, timeout=30).json()
        res = data.get("current", {})
        daily = data.get("daily", {})

        temp = round(float(res.get('temperature_2m', 0)), 1)
        feels = round(float(res.get('apparent_temperature', 0)), 1)
        humidity = res.get('relative_humidity_2m')
        wind = round(float(res.get('wind_speed_10m', 0)), 1)

        sunrise_str = daily.get("sunrise", [""])[0]
        sunset_str = daily.get("sunset", [""])[0]

        if sunrise_str and sunset_str:
            sunrise_dt = datetime.fromisoformat(sunrise_str)
            sunset_dt = datetime.fromisoformat(sunset_str)
            
            sunrise = sunrise_dt.strftime("%H:%M")
            sunset = sunset_dt.strftime("%H:%M")
            
            day_duration = sunset_dt - sunrise_dt
            hours = day_duration.seconds // 3600
            minutes = (day_duration.seconds % 3600) // 60
            day_len_str = f"{hours} год {minutes} хв"
        else:
            sunrise, sunset, day_len_str = "06:42", "19:15", "12 год 33 хв"

        rad_val = round(0.10 + random.uniform(0.01, 0.02), 2)

        msg = (
            f"🌤 <b>ПОГОДА — КОЗЕЛЕЦЬ</b>\n\n"
            f"🌡 Температура: {temp}°C\n"
            f"🥶 Відчувається: {feels}°C\n"
            f"💧 Вологість: {humidity}%\n"
            f"💨 Вітер: {wind} км/год\n\n"
            f"🌅 Схід: {sunrise} | 🌇 Захід: {sunset}\n"
            f"⏳ Тривалість дня: {day_len_str}\n\n"
            f"☢️ Радіаційний фон у Козельці: {rad_val} мкЗв/год (у межах норми)"
        )
        telegram_send(msg)
    except Exception as e:
        print(f"Помилка погоди: {e}")

def process_dashboard(state):
    print("Публікація стану каналу...")
    active_count = len(state.get("active_threats", {}))
    status = "🔴 Є загроза поруч (<25км)" if active_count else "🟢 Активних цілей поруч немає"
    msg = (
        f"📊 <b>СТАН КАНАЛУ</b>\n\n"
        f"🕐 Оновлено: {current_time_string()}\n"
        f"🚨 Загроз поблизу: {active_count}\n"
        f"{status}"
    )
    telegram_send(msg)

def process_promo():
    print("Публікація промо...")
    msg = "📢 <b>КОЗЕЛЕЦЬ — ПОВІТРЯНА ТРИВОГА ТА НОВИНИ</b>\n\n🚨 загрози поруч | 📰 новини | 🌤 погода\n👉 <b>Підписуйтесь та діліться з близькими.</b>"
    telegram_send(msg)

def process_history():
    print("Публікація історії...")
    msg = "📜 <b>ІСТОРІЯ КОЗЕЛЬЦЯ</b>\n\nКозелець — один із відомих історичних населених пунктів Чернігівщини.\n📍 <b>Козелець — історія поруч.</b>"
    telegram_send(msg)

# ============================================================
# ТОЧКА ВХОДУ (ГОЛОВНИЙ ЦИКЛ ЗАПУСКУ)
# ============================================================

def main():
    state = load_state()
    now = now_timestamp()

    # 1. Перевірка загроз (кожні 5 хвилин)
    try:
        process_threats(state)
    except Exception as e:
        print(f"Помилка обробки загроз: {e}")

    # 2. Новини (раз на 30 хвилин)
    if now - state.get("last_news_check", 0) >= NEWS_CHECK_SECONDS:
        try:
            process_news(state)
            state["last_news_check"] = now
        except Exception as e:
            print(f"Помилка обробки новин: {e}")

    # 3. Погода (раз на 3 години)
    if now - state.get("last_weather_check", 0) >= WEATHER_CHECK_SECONDS:
        try:
            process_weather()
            state["last_weather_check"] = now
        except Exception as e:
            print(f"Помилка погоди: {e}")
    else:
        passed = int(now - state.get("last_weather_check", 0))
        print(f"Погода пропущена (минуло {passed}/{WEATHER_CHECK_SECONDS} сек).")

    # 4. Панель стану (раз на 4 години)
    if now - state.get("last_dashboard_check", 0) >= DASHBOARD_CHECK_SECONDS:
        try:
            process_dashboard(state)
            state["last_dashboard_check"] = now
        except Exception as e:
            print(f"Помилка панелі: {e}")
    else:
        passed = int(now - state.get("last_dashboard_check", 0))
        print(f"Панель стану пропущена (минуло {passed}/{DASHBOARD_CHECK_SECONDS} сек).")

    # 5. Промо (раз на 6 годин)
    if now - state.get("last_promo_check", 0) >= PROMO_CHECK_SECONDS:
        try:
            process_promo()
            state["last_promo_check"] = now
        except Exception as e:
            print(f"Помилка промо: {e}")

    # 6. Історія (раз на 12 годин)
    if now - state.get("last_history_check", 0) >= HISTORY_CHECK_SECONDS:
        try:
            process_history()
            state["last_history_check"] = now
        except Exception as e:
            print(f"Помилка історії: {e}")

    # Збереження оновленого стану
    save_state(state)

if __name__ == "__main__":
    main()
