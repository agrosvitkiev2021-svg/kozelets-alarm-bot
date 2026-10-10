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

# Ваш особистий юзернейм для кнопки «Запропонувати новину»
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Kasper081297").replace("@", "").strip()

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

# Вечірній дайджест — раз на добу
DIGEST_CHECK_SECONDS = 24 * 60 * 60


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
# ІСТОРІЯ ТА ПАМ'ЯТКИ КОЗЕЛЕЧЧИНИ
# ============================================================

LOCAL_HISTORY_POSTS = [
    (
        "🏛 <b>Історія Козельця: Заснування та козацьке минуле</b>\n\n"
        "У XV столітті неподалік від Остра з’явилося поселення Козелець. На початку XVII століття це було вже значне укріплене місто, мешканці якого активно займалися рибальством.\n\n"
        "📌 <i>Цікавий факт:</i> У 1649 році тут сформувалась козацька сотня Київського полку. У 1654 році місто увійшло до складу Російської держави, а в 1656 році отримало Магдебурзьке право. У 1708 році Козелець став центром управління Київського козацького полку!"
    ),
    (
        "👑 <b>Родина Розумовських і Собор Різдва Богородиці</b>\n\n"
        "Найстарішою та найефектнішою спорудою Козельця є величний <b>Собор Різдва Богородиці</b>, збудований за проектом Растреллі архітекторами І. Григоровичем-Барським та А. Квасовим.\n\n"
        "Будівництво ініціювала родина Розумовських. Олексій Розумовський пройшов шлях від співака в церковному хорі до графа та таємного чоловіка імператриці Єлизавети Петрівни. Його молодший брат Кирило став останнім гетьманом України (1750–1764).\n\n"
        "✨ Фундаторкою храму стала їхня мати Наталія Дем’янівна. Будівництво тривало 11 років (1752–1763). Храм вражає своєю п’ятибанною архітектурою, розкішною ліпниною та унікальним 27-метровим іконостасом!"
    ),
    (
        "🏛 <b>Будинок полкової канцелярії (Магістрат)</b>\n\n"
        "Ще одну видатну пам’ятку Козельця — будинок полкової канцелярії — будували дев'ять років (1756–1765) на замовлення полковника Юхима Дарагана.\n\n"
        "📌 <i>Цікавий факт:</i> Після скасування полкового устрою в 1781 році будівля виконувала функції козелецького магістрату. Сьогодні в цій історичній будівлі розташована районна бібліотека."
    ),
    (
        "⛪ <b>Миколаївська та Вознесенська церкви у Козельці</b>\n\n"
        "• <b>Миколаївська церква (1781–1784)</b> збудована в стилі пізнього бароко на кошти священника Кирила Тарловського на пагорбі біля в'їзду до Київської слобідки. У травні 1861 року тут зупинялася траурна процесія з прахом Тараса Шевченка, і місцевий священник відслужив панахиду за Кобзарем.\n\n"
        "• <b>Вознесенська церква (1866–1874)</b> зведена в період історизму з використанням мотивів української архітектури. Чотири її декоративні верхи нагадують оборонні вежі. Довгий час тут розміщувався музей історії ткацтва Чернігівщини."
    ),
    (
        "🏡 <b>Садиба Дараганів та кам’яниця у Покорщині</b>\n\n"
        "На околиці Козельця (у колишньому селі Покорщина) збереглася садиба полковника Юхима Дарагана. У 1975 році тут навіть знімали радянський фільм «Звезда пленительного щастья» про декабристів.\n\n"
        "📌 <i>Цікавий факт:</i> Унікальною будівлею садиби є <b>кам’яниця</b> середини XVIII століття, яка виконувала господарські та фортифікаційні функції (тут був арсенал Дараганів і льох)."
    ),
    (
        "⛪ <b>Зникла Преображенська церква та сучасні події</b>\n\n"
        "Найстарішим і головним храмом Козельця колись була <b>Преображенська церква</b>, відома з початку XVII ст. У радянські часи її було зруйновано, а на її місці збудовано адміністративну будівлю (де нині розміщуються районний суд та служби).\n\n"
        "✨ А у 2004 році в соборі Різдва Богородиці відбулося вінчання Андрія Розумовського — прямого нащадка останнього гетьмана Кирила Розумовського, який прибув до Козельця з далекої Аргентини разом із нареченою Урсулою!"
    ),
    (
        "🏛 <b>Трьохсвятительська церква у селі Лемеші</b>\n\n"
        "У селі Лемеші поблизу Козельця розташована унікальна кам'яна <b>Трьохсвятительська церква</b> (1755–1760 рр.), збудована у стилі бароко над могилою батька Олексія та Кирила Розумовських — Григорія Розума.\n\n"
        "📌 <i>Цікавий факт:</i> У 1913–1914 роках інтер'єр і розписи храму реставрували видатні українські митці Михайло Бойчук та його дружина Софія Налепинська-Бойчук (на жаль, у радянські часи ці унікальні розписи та іконостас були знищені)."
    ),
    (
        "🌿 <b>Данівський Свято-Георгіївський монастир</b>\n\n"
        "Монастир у селі Данівка був заснований у 1654 році ченцями Козелецького Свято-Троїцького монастиря на честь перемоги під час Хмельниччини.\n\n"
        "✨ Головний Георгіївський собор побудований у 1741–1754 роках за підтримки полковника Юхима Дарагана і є одним із найкращих зразків архітектури XVIII століття з елементами оборонного стилю. Сьогодні в монастирі зберігається чудотворна ікона Богородиці «Аз єсмь з вами і ніктоже на ви»."
    )
]

DAILY_OMENS = [
    "🌿 <b>Народні прикмети на сьогодні:</b> якщо зранку туман стелиться низько — буде тепла погода без опадів; птахи високо в небі — до сонячного дня.",
    "🌾 <b>Сьогоднішні прикмети:</b> тихий вітер та ясне небо віщують спокійний і сприятливий день для господарських робіт.",
    "☀️ <b>Народна мудрість:</b> ранкова роса та сонячні промені з самого ранку обіцяють гарний урожай та вдалий тиждень."
]

PROMO_POSTS = [
    (
        "📢 <b>Долучайтеся до нашої спільноти!</b>\n\n"
        "Запрошуйте друзів та знайомих до нашого каналу — оперативні новини, безпека та історія Козелеччини разом.\n\n"
        "🔗 Поділіться посиланням на канал з тими, хто тут мешкає!"
    )
]


# ============================================================
# TELEGRAM API ТА КНОПКИ
# ============================================================

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram_send(text, show_buttons=True, comment_url=None):
    """
    Відправка повідомлення в Telegram із розширеними Inline-кнопками.
    """
    try:
        clean_channel = CHANNEL.replace("@", "").strip()
        channel_link = f"https://t.me/{clean_channel}"
        
        share_text = "Оперативні сповіщення, тривоги та новини Козелеччини! 🔔"
        share_url = (
            f"https://t.me/share/url?"
            f"url={requests.utils.quote(channel_link)}&"
            f"text={requests.utils.quote(share_text)}"
        )
        
        admin_link = f"https://t.me/{ADMIN_USERNAME}"

        data = {
            "chat_id": CHANNEL,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        if show_buttons:
            discussion_link = comment_url if comment_url else channel_link
            
            reply_markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": "📢 Поділитися",
                            "url": share_url
                        },
                        {
                            "text": "💬 Обговорити",
                            "url": discussion_link
                        }
                    ],
                    [
                        {
                            "text": "✍️ Запропонувати новину",
                            "url": admin_link
                        }
                    ]
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
        "active_threats": {},
        "last_threat_update": 0,
        "last_news_check": 0,
        "published_news": [],
        "last_weather_check": 0,
        "last_promo_check": 0,
        "last_history_check": 0,
        "published_history_indexes": [],
        "last_digest_check": 0,
        "district_alert_active": None,
        "district_alert_initialized": False,
    }


def load_state():
    if not STATE_FILE.exists():
        print("ℹ️ bot_state.json не знайдено. Створюю новий стан.")
        return default_state()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)

        base = default_state()
        base.update(state)
        return base

    except Exception as e:
        print(f"⚠️ Помилка читання bot_state.json: {e}")
        return default_state()


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
        print("💾 Стан бота збережено.")
    except Exception as e:
        print(f"❌ Помилка збереження bot_state.json: {e}")


# ============================================================
# ЧАС ТА КУРСИ ВАЛЮТ НБУ
# ============================================================

def now_timestamp():
    return datetime.now(timezone.utc).timestamp()


def kyiv_time():
    return datetime.now(timezone.utc) + timedelta(hours=3)


def current_time_string():
    return kyiv_time().strftime("%H:%M")


def get_nbu_rates():
    """Отримання актуального курсу USD та EUR від НБУ"""
    try:
        response = requests.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json", timeout=10)
        if response.status_code == 200:
            data = response.json()
            rates = {}
            for item in data:
                if item.get("cc") in ["USD", "EUR"]:
                    rates[item.get("cc")] = round(item.get("rate"), 2)
            return rates
    except Exception as e:
        print(f"⚠️ Помилка отримання курсів НБУ: {e}")
    return {}


# ============================================================
# ГЕОЛОКАЦІЯ
# ============================================================

def distance_km(lat1, lon1, lat2, lon2):
    try:
        radius = 6371.0
        lat1 = math.radians(float(lat1))
        lon1 = math.radians(float(lon1))
        lat2 = math.radians(float(lat2))
        lon2 = math.radians(float(lon2))

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c
    except Exception:
        return None


def nearest_place(lat, lon):
    best_name = None
    best_distance = None

    for name, coords in PLACES.items():
        distance = distance_km(lat, lon, coords[0], coords[1])
        if distance is None:
            continue
        if best_distance is None or distance < best_distance:
            best_name = name
            best_distance = distance

    return best_name, best_distance


def get_value(data, *keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None


# ============================================================
# ОФІЦІЙНА ПОВІТРЯНА ТРИВОГА (ЧЕРНІГІВСЬКИЙ РАЙОН)
# ============================================================

def get_district_alert():
    print(f"🚨 Перевіряю офіційний API: {AIR_REGION_NAME}...")
    headers = {
        "Authorization": AIR_API_TOKEN,
        "Accept": "application/json",
        "User-Agent": "KozeletsAlarmBot/1.0",
    }
    try:
        response = requests.get(AIR_API_URL, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
        return parse_district_alert(response.json())
    except Exception as e:
        print(f"❌ Помилка UkraineAlarm: {e}")
        return None


def parse_district_alert(data):
    item = None
    if isinstance(data, list):
        if len(data) == 0:
            return False
        item = data[0]
    elif isinstance(data, dict):
        if "activeAlerts" in data or "regionName" in data:
            item = data
        elif isinstance(data.get("states"), list):
            for state in data["states"]:
                state_id = get_value(state, "regionId", "id", "region_id")
                if str(state_id) == str(AIR_REGION_ID):
                    item = state
                    break
            if item is None and data["states"]:
                item = data["states"][0]

    if not isinstance(item, dict):
        return None

    active_alerts = item.get("activeAlerts")
    if isinstance(active_alerts, (list, dict)):
        active = len(active_alerts) > 0
    elif isinstance(active_alerts, bool):
        active = active_alerts
    else:
        active = bool(get_value(item, "active", "isActive"))

    return active


def process_district_alert(state):
    current_alert = get_district_alert()
    if current_alert is None:
        return

    previous_alert = state.get("district_alert_active")
    initialized = state.get("district_alert_initialized", False)

    if not initialized:
        state["district_alert_active"] = current_alert
        state["district_alert_initialized"] = True
        if current_alert:
            telegram_send(
                "🔴 <b>ПОВІТРЯНА ТРИВОГА</b>\n\n"
                f"📍 <b>{html.escape(AIR_REGION_NAME)}</b>\n\n"
                "⚠️ У районі оголошено повітряну тривогу.\n\n"
                f"🕐 Час: {current_time_string()}",
                show_buttons=False
            )
        return

    if current_alert is True and previous_alert is not True:
        message = (
            "🔴 <b>ПОВІТРЯНА ТРИВОГА</b>\n\n"
            f"📍 <b>{html.escape(AIR_REGION_NAME)}</b>\n\n"
            "⚠️ У районі оголошено повітряну тривогу.\n\n"
            f"🕐 Час початку: {current_time_string()}\n\n"
            "🚨 Перейдіть у безпечне місце та дотримуйтесь правил безпеки."
        )
        if telegram_send(message, show_buttons=False):
            state["district_alert_active"] = True

    elif current_alert is False and previous_alert is True:
        message = (
            "🟢 <b>ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ</b>\n\n"
            f"📍 <b>{html.escape(AIR_REGION_NAME)}</b>\n\n"
            "✅ У районі оголошено відбій повітряної тривоги.\n\n"
            f"🕐 Час відбою: {current_time_string()}"
        )
        if telegram_send(message, show_buttons=False):
            state["district_alert_active"] = False

    else:
        state["district_alert_active"] = current_alert


# ============================================================
# NEPTUN
# ============================================================

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
        if normalized in ("missile", "rocket"):
            return "Ракета"
        if normalized == "ballistic":
            return "Балістична ракета"
        return str(threat_type)
    return str(title) if title else "Невідома загроза"


def get_neptun_threats():
    try:
        response = requests.get(NEPTUN_API, timeout=30)
        if response.status_code != 200:
            return []
        data = response.json()
        return data.get("threats", []) if isinstance(data, dict) else data
    except Exception:
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
    place, distance = (None, None)
    if lat is not None and lon is not None and not area_only:
        place, distance = nearest_place(lat, lon)

    display_place = place or "Козелеччина / поблизу"
    threat_type = threat_type_name(threat)

    message = [
        "🛰 <b>ПОВІТРЯНА ЗАГРОЗА ПОБЛИЗУ</b>\n",
        f"⚠️ <b>Тип:</b> {html.escape(str(threat_type))}",
        f"📍 <b>Район:</b> {html.escape(str(display_place))}",
    ]
    if distance is not None and not area_only:
        message.append(f"📏 <b>Відстань:</b> ~{distance:.1f} км")
    message.append(f'\n🔗 <a href="{NEPTUN_URL}">Карта Neptun</a>')
    return "\n".join(message)


def process_threats(state):
    threats = get_neptun_threats()
    current = {}
    for threat in threats:
        if not isinstance(threat, dict) or not is_active_threat(threat):
            continue
        if bool(threat.get("areaOnly", False)):
            continue
        lat, lon = extract_coordinates(threat)
        if lat is None or lon is None:
            continue
        place, distance = nearest_place(lat, lon)
        if place is None or distance is None or distance > THREAT_RADIUS_KM:
            continue
        current[make_threat_id(threat)] = threat

    previous = state.get("active_threats", {})
    if not isinstance(previous, dict):
        previous = {}

    new_ids = [tid for tid in current if tid not in previous]
    for tid in new_ids:
        telegram_send(build_threat_message(current[tid]), show_buttons=False)

    now = now_timestamp()
    last_update = state.get("last_threat_update", 0)
    if current and not new_ids and (now - last_update >= THREAT_UPDATE_SECONDS):
        for tid, threat in list(current.items())[:3]:
            telegram_send(build_threat_message(threat), show_buttons=False)
        state["last_threat_update"] = now

    if previous and not current:
        telegram_send("🟢 <b>ВІДБІЙ ПОБЛИЗУ</b>\n\nУ радіусі 25 км активних цілей не виявлено.", show_buttons=False)
        state["last_threat_update"] = now

    if not previous and current:
        state["last_threat_update"] = now

    state["active_threats"] = current


# ============================================================
# НОВИНИ
# ============================================================

def process_news(state):
    print("📰 Обробка новин...")
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

                if published_time is None or (now - published_time) > NEWS_MAX_AGE_MINUTES * 60:
                    continue

                item_id = hashlib.md5((title + "|" + link).encode("utf-8")).hexdigest()
                if item_id in published_set:
                    continue

                message = (
                    "📰 <b>НОВИНА</b>\n\n"
                    f"📍 <b>{html.escape(source_name)}</b>\n"
                    f"{html.escape(title)}\n\n"
                    f'<a href="{html.escape(link, quote=True)}">🔗 Читати новину</a>'
                )

                if telegram_send(message):
                    published.append(item_id)
                    published_set.add(item_id)
        except Exception as e:
            print(f"❌ Помилка RSS {source_name}: {e}")

    state["published_news"] = published[-500:]


# ============================================================
# ПОГОДА ТА ШТОРМОВІ ПОПЕРЕДЖЕННЯ
# ============================================================

def process_weather():
    print("🌤 Публікація погоди...")
    lat, lon = PLACES["Козелець"]
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m"
        "&daily=sunrise,sunset"
        "&timezone=Europe%2FKyiv"
    )

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        current = data.get("current", {})
        daily = data.get("daily", {})

        temp = round(float(current.get("temperature_2m", 0)), 1)
        feels = round(float(current.get("apparent_temperature", 0)), 1)
        humidity = current.get("relative_humidity_2m")
        wind = round(float(current.get("wind_speed_10m", 0)), 1)

        sunrise_str = daily.get("sunrise", [""])[0]
        sunset_str = daily.get("sunset", [""])[0]

        if sunrise_str and sunset_str:
            sunrise_dt = datetime.fromisoformat(sunrise_str)
            sunset_dt = datetime.fromisoformat(sunset_str)
            sunrise = sunrise_dt.strftime("%H:%M")
            sunset = sunset_dt.strftime("%H:%M")
            day_len = sunset_dt - sunrise_dt
            mins = int(day_len.total_seconds() // 60)
            day_len_str = f"{mins // 60} год {mins % 60} хв"
        else:
            sunrise, sunset, day_len_str = "—", "—", "—"

        storm_warning = ""
        if wind > 14:
            storm_warning = "\n⚠️ <b>УВАГА: Штормове попередження!</b> Сильний вітер, будьте обережні.\n"

        omen = random.choice(DAILY_OMENS)

        msg = (
            "🌤 <b>ПОГОДА — КОЗЕЛЕЦЬ</b>\n\n"
            f"🌡 Температура: {temp}°C (відчувається як {feels}°C)\n"
            f"💧 Вологість: {humidity}% | 💨 Вітер: {wind} м/с\n"
            f"🌅 Схід: {sunrise} | 🌇 Захід: {sunset}\n"
            f"⏳ Тривалість дня: {day_len_str}\n"
            f"{storm_warning}\n"
            f"{omen}\n\n"
            f"🕐 Оновлено: {current_time_string()}"
        )

        telegram_send(msg)
    except Exception as e:
        print(f"❌ Помилка погоди: {e}")


# ============================================================
# ІСТОРІЯ ТА ДАЙДЖЕСТ
# ============================================================

def process_history(state):
    print("📜 Публікація історичного факту...")
    published = state.get("published_history_indexes", [])
    if len(published) >= len(LOCAL_HISTORY_POSTS):
        published = []

    available = [i for i in range(len(LOCAL_HISTORY_POSTS)) if i not in published]
    if not available:
        return

    idx = random.choice(available)
    if telegram_send(LOCAL_HISTORY_POSTS[idx]):
        published.append(idx)
        state["published_history_indexes"] = published


def process_digest(state):
    print("🌙 Публікація вечірнього дайджесту...")
    rates = get_nbu_rates()
    usd = rates.get("USD", "—")
    eur = rates.get("EUR", "—")

    msg = (
        "🌙 <b>ВЕЧІРНІЙ ДАЙДЖЕСТ — КОЗЕЛЕЧЧИНА</b>\n\n"
        f"💱 <b>Офіційний курс НБУ:</b>\n"
        f"• USD: <b>{usd} грн</b>\n"
        f"• EUR: <b>{eur} грн</b>\n\n"
        "📌 Доббігає кінця день. Дякуємо Силам оборони України за кожну спокійну годину.\n"
        "Дотримуйтеся правил безпеки та бережіть себе!\n\n"
        f"🕐 <i>Підсумок станом на {current_time_string()}</i>"
    )
    telegram_send(msg)


def process_promo():
    print("📢 Публікація промо-посту...")
    if PROMO_POSTS:
        telegram_send(random.choice(PROMO_POSTS))


# ============================================================
# ГОЛОВНА ЛОГІКА ЗАПУСКУ
# ============================================================

def main():
    state = load_state()
    now = now_timestamp()

    # 1. Офіційна тривога району
    process_district_alert(state)

    # 2. Загрози Neptun (25 км)
    process_threats(state)

    # 3. Новини
    if now - state.get("last_news_check", 0) >= NEWS_CHECK_SECONDS:
        process_news(state)
        state["last_news_check"] = now

    # 4. Погода
    if now - state.get("last_weather_check", 0) >= WEATHER_CHECK_SECONDS:
        process_weather()
        state["last_weather_check"] = now

    # 5. Історія / Краєзнавство
    if now - state.get("last_history_check", 0) >= HISTORY_CHECK_SECONDS:
        process_history(state)
        state["last_history_check"] = now

    # 6. Вечірній дайджест (перевірка раз на добу)
    if now - state.get("last_digest_check", 0) >= DIGEST_CHECK_SECONDS:
        process_digest(state)
        state["last_digest_check"] = now

    # 7. Промо
    if now - state.get("last_promo_check", 0) >= PROMO_CHECK_SECONDS:
        process_promo()
        state["last_promo_check"] = now

    save_state(state)


if __name__ == "__main__":
    main()
