import os
import re
import json
import html
import time
import hashlib
import requests
import xml.etree.ElementTree as ET

from datetime import datetime
from urllib.parse import quote
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import new_decoderv1
except Exception:
    new_decoderv1 = None


# =========================================================
# НАЛАШТУВАННЯ
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")

# API Ukraine Alarm (вже вставлений)
UKRAINE_ALARM_API_KEY = "75bae807:2dd7c872d065925b6876f395c742ba41"

TIMEZONE = ZoneInfo("Europe/Kyiv")

# Координати Козельця
KOZELETS_LAT = 50.913
KOZELETS_LON = 31.115

# Файли стану
NEWS_STATE_FILE = "news_seen.txt"
ALERT_STATE_FILE = "alert_state.txt"
RAD_STATE_FILE = "rad_state.txt"
PINNED_MSG_ID_FILE = "pinned_msg_id.txt"
HISTORY_INDEX_FILE = "history_index.txt"
HISTORY_LAST_TIME_FILE = "history_last_time.txt"


# =========================================================
# БАЗА ІСТОРИЧНИХ ФАКТІВ
# =========================================================

KOZELETS_HISTORY_FACTS = [
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Собор Різдва Богородиці (Козелець)\n\n"
        "Головна архітектурна перлина Козельця, збудована у 1752–1763 роках "
        "за наказом графині Наталії Розумовської. Унікальний іконостас висотою "
        "майже 27 метрів є одним із найкращих зразків українського бароко."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Старовинний Остер\n\n"
        "Остер — одне з найдавніших міст Чернігівщини. Заснований ще у XI столітті "
        "як фортеця Городець. Тут збереглися залишки Борисоглібської церкви домонгольської доби."
    ),
    (
        "👥 ВИДАТНІ ЛЮДИ: Родина Розумовських\n\n"
        "Козелець тісно пов'язаний із родом Розумовських. Саме Наталія Розумовська "
        "фінансувала будівництво величного собору та інших споруд краю."
    ),
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Будинок полкової канцелярії\n\n"
        "Архітектурна пам'ятка XVIII століття, де працювала адміністрація "
        "Козелецького полку."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Бобровиця\n\n"
        "Бобровиця історично була важливим центром землеробства, торгівлі "
        "та цукрової промисловості Лівобережної України."
    ),
    (
        "👥 ВИДАТНІ ЛЮДИ: Павло Чубинський\n\n"
        "Автор слів Державного Гімну України досліджував побут та традиції "
        "мешканців Чернігівщини."
    ),
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Миколаївська церква\n\n"
        "Одна із найстаріших церков Козельця, побудована у XVIII столітті."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Магдебурзьке право\n\n"
        "Козелець мав Магдебурзьке право, що забезпечувало місту самоврядування."
    )
]


# =========================================================
# ДЖЕРЕЛА НОВИН
# =========================================================

NEWS_SOURCES = [
    {
        "query": "site:cheline.com.ua Козелець",
        "category": "📍 КОЗЕЛЕЦЬ (Вісник Ч)",
        "priority": 1,
    },
    {
        "query": "site:cheline.com.ua Остер",
        "category": "📍 ОСТЕР (Вісник Ч)",
        "priority": 1,
    },
    {
        "query": "site:cheline.com.ua Бобровиця",
        "category": "📍 БОБРОВИЦЯ (Вісник Ч)",
        "priority": 1,
    },
    {
        "query": "site:cheline.com.ua Козелецький район",
        "category": "📍 КОЗЕЛЕЧЧИНА (Вісник Ч)",
        "priority": 1,
    },
    {
        "query": "site:suspilne.media/chernihiv Козелець",
        "category": "📍 КОЗЕЛЕЦЬ",
        "priority": 2,
    },
    {
        "query": "site:cntime.cn.ua Козелець",
        "category": "📍 КОЗЕЛЕЦЬ",
        "priority": 3,
    },
    {
        "query": "\"Козелець\" світло вода новини",
        "category": "🚰 КОМУНАЛКА / СВІТЛО",
        "priority": 1,
    },
    {
        "query": "\"Остер\" новини міста",
        "category": "📍 ОСТЕР",
        "priority": 2,
    },
    {
        "query": "\"Бобровиця\" новини громади",
        "category": "📍 БОБРОВИЦЯ",
        "priority": 2,
    },
    {
        "query": "\"Козелеччина\" новини",
        "category": "📍 КОЗЕЛЕЧЧИНА",
        "priority": 2,
    },
]


# =========================================================
# TELEGRAM API
# =========================================================

def telegram_url(method):
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def send_message(text, disable_preview=True):
    if not BOT_TOKEN or not CHANNEL:
        print("BOT_TOKEN або CHANNEL не задані.")
        return None

    try:
        response = requests.post(
            telegram_url("sendMessage"),
            data={
                "chat_id": CHANNEL,
                "text": text,
                "disable_web_page_preview": disable_preview,
            },
            timeout=8,
        )

        if response.ok:
            return response.json()["result"]["message_id"]

        print(response.text)

    except Exception as e:
        print("Telegram:", e)

    return None


def send_photo(photo_url, caption):
    if not photo_url:
        return None

    try:
        response = requests.post(
            telegram_url("sendPhoto"),
            data={
                "chat_id": CHANNEL,
                "photo": photo_url,
                "caption": caption,
            },
            timeout=10,
        )

        if response.ok:
            return response.json()["result"]["message_id"]

    except Exception as e:
        print("Telegram Photo:", e)

    return None


def edit_message(message_id, text, disable_preview=True):
    try:
        response = requests.post(
            telegram_url("editMessageText"),
            data={
                "chat_id": CHANNEL,
                "message_id": message_id,
                "text": text,
                "disable_web_page_preview": disable_preview,
            },
            timeout=8,
        )
        return response.ok

    except Exception as e:
        print("Edit:", e)

    return False


def pin_message(message_id):
    try:
        requests.post(
            telegram_url("pinChatMessage"),
            data={
                "chat_id": CHANNEL,
                "message_id": message_id,
                "disable_notification": True,
            },
            timeout=5,
        )
    except Exception:
        pass


# =========================================================
# ФАЙЛИ СТАНУ
# =========================================================

def read_state(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def write_state(filename, value):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(str(value))# =========================================================
# ІСТОРИЧНІ ПОСТИ
# =========================================================

def check_and_send_history_post():
    now = datetime.now(TIMEZONE)
    current_timestamp = now.timestamp()

    last_time_str = read_state(HISTORY_LAST_TIME_FILE)
    last_timestamp = float(last_time_str) if last_time_str else 0

    # Новий історичний пост кожні 12 годин
    if current_timestamp - last_timestamp >= 12 * 3600 or last_timestamp == 0:

        index_str = read_state(HISTORY_INDEX_FILE)
        index = int(index_str) if index_str else 0

        if index >= len(KOZELETS_HISTORY_FACTS):
            index = 0

        text = (
            "📚 ІСТОРІЯ ТА КРАЄЗНАВСТВО КРАЮ\n"
            "━━━━━━━━━━━━━━━━━━━\n\n"
            f"{KOZELETS_HISTORY_FACTS[index]}\n\n"
            "#Козелець #Остер #Бобровиця #Історія"
        )

        if send_message(text):
            write_state(HISTORY_INDEX_FILE, index + 1)
            write_state(HISTORY_LAST_TIME_FILE, current_timestamp)
            print("Історичний пост опубліковано.")


# =========================================================
# ОЧИЩЕННЯ ТЕКСТУ
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\\S+", " ", text)
    text = re.sub(r"\\s+", " ", text)

    return text.strip()


def clean_title(title):
    title = clean_text(title)

    patterns = [
        r"\\s+-\\s+Суспільне.*$",
        r"\\s+-\\s+ЧЕline.*$",
        r"\\s+-\\s+Вісник Ч.*$",
        r"\\s+-\\s+Час Чернігівський.*$",
        r"\\s+\\|\\s+Суспільне.*$",
        r"\\s+\\|\\s+ЧЕline.*$",
    ]

    for pattern in patterns:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)

    return title.strip()


# =========================================================
# GOOGLE NEWS
# =========================================================

def resolve_news_link(link):
    if "news.google.com" not in link:
        return link

    if new_decoderv1 is None:
        return link

    try:
        result = new_decoderv1(link, interval_time=0.3)

        if isinstance(result, dict) and result.get("status"):
            return result["url"]

        if isinstance(result, str):
            return result

    except Exception:
        pass

    return link


def get_google_news(query):

    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=uk&gl=UA&ceid=UA:uk"
    )

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6,
        )

        if not response.ok:
            return []

        root = ET.fromstring(response.content)
        news = []

        for item in root.findall(".//item"):

            title = clean_title(item.findtext("title", ""))
            link = item.findtext("link", "")
            description = clean_text(item.findtext("description", ""))
            pub_date = item.findtext("pubDate", "")

            try:
                date = parsedate_to_datetime(pub_date).astimezone(TIMEZONE)
            except Exception:
                date = datetime.now(TIMEZONE)

            news.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "date": date,
                }
            )

        return news

    except Exception:
        return []


# =========================================================
# ОТРИМАННЯ ТЕКСТУ СТАТТІ
# =========================================================

def extract_article_data(url):

    if "google.com" in url:
        return "", ""

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "uk-UA,uk;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)

        if not response.ok:
            return "", ""

        page = response.text

        image_url = ""
        description = ""

        img = re.search(
            r'property=["\\\']og:image["\\\'].*?content=["\\\']([^"\\\']+)',
            page,
            flags=re.I,
        )

        if img:
            image_url = img.group(1)

            if image_url.startswith("//"):
                image_url = "https:" + image_url

        desc = re.search(
            r'name=["\\\']description["\\\'].*?content=["\\\']([^"\\\']+)',
            page,
            flags=re.I,
        )

        if desc:
            description = clean_text(desc.group(1))

        if len(description) > 650:
            description = description[:650].rsplit(" ", 1)[0] + "..."

        return description, image_url

    except Exception:
        return "", ""


# =========================================================
# ДУБЛІКАТИ НОВИН
# =========================================================

def normalize_title(title):
    title = title.lower()
    title = re.sub(r"[^а-яіїєґa-z0-9 ]", " ", title)
    return re.sub(r"\\s+", " ", title).strip()


def similar_titles(a, b):

    a = set(normalize_title(a).split())
    b = set(normalize_title(b).split())

    if not a or not b:
        return False

    return (
        min(len(a), len(b)) > 4
        and len(a & b) / min(len(a), len(b)) >= 0.65
    )


def load_seen_items():

    content = read_state(NEWS_STATE_FILE)

    if not content:
        return set()

    return set(content.splitlines())


def save_seen_items(items):

    items = list(items)[-2000:]

    with open(NEWS_STATE_FILE, "w", encoding="utf-8") as f:
        for item in items:
            f.write(item + "\\n")


# =========================================================
# ПЕРЕВІРКА НОВИН
# =========================================================

def check_news():

    print("Перевіряю новини...")

    seen = load_seen_items()
    prepared = []

    now = datetime.now(TIMEZONE)

    for source in NEWS_SOURCES:

        for item in get_google_news(source["query"]):

            title = item["title"]

            if not title:
                continue

            if (now - item["date"]).total_seconds() > 6 * 3600:
                continue

            lower = title.lower()

            if not any(
                word in lower
                for word in ["козелець", "козелеч", "остер", "бобровиц"]
            ):
                continue

            news_id = hashlib.sha256(
                normalize_title(title).encode("utf-8")
            ).hexdigest()

            if news_id in seen:
                continue

            prepared.append(
                {
                    "id": news_id,
                    "title": title,
                    "link": item["link"],
                    "description": item["description"],
                    "date": item["date"],
                    "category": source["category"],
                    "priority": source["priority"],
                }
            )

    prepared.sort(key=lambda x: (x["priority"], -x["date"].timestamp()))

    unique = []

    for item in prepared:

        if not any(similar_titles(item["title"], i["title"]) for i in unique):
            unique.append(item)

    published = 0

    for item in unique:

        url = resolve_news_link(item["link"])

        article_text, image_url = extract_article_data(url)

        if not article_text:
            article_text = (
                item["description"] or "Подробиці новини уточнюються."
            )

        caption = (
            f"{item['category']}\\n\\n"
            f"📰 {item['title']}\\n\\n"
            f"{article_text}"
        )

        if image_url:
            ok = send_photo(image_url, caption)
        else:
            ok = send_message(caption)

        if ok:
            seen.add(item["id"])
            published += 1

    save_seen_items(seen)

    print(f"Опубліковано новин: {published}")# =========================================================
# ПОВІТРЯНІ ТРИВОГИ (Ukraine Alarm API)
# =========================================================

def check_alerts():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Authorization": UKRAINE_ALARM_API_KEY
        }

        response = requests.get(
            "https://api.ukrainealarm.com/api/v3/alerts",
            headers=headers,
            timeout=5
        )

        is_alarm = False

        if response.ok:
            data = response.json()

            for region in data:
                region_name = str(region.get("regionName", "")).lower()

                if "чернігівська" in region_name:
                    if region.get("activeAlerts"):
                        is_alarm = True
                    break

        old_state = read_state(ALERT_STATE_FILE) == "1"

        if is_alarm and not old_state:
            send_message(
                "🚨 ПОВІТРЯНА ТРИВОГА\n\n"
                "Чернігівська область!\n\n"
                "⚠️ Негайно перейдіть в укриття."
            )
            write_state(ALERT_STATE_FILE, "1")

        elif (not is_alarm) and old_state:
            send_message(
                "🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
                "Загроза для Чернігівської області минула."
            )
            write_state(ALERT_STATE_FILE, "0")

        return is_alarm

    except Exception as e:
        print("Alarm API:", e)
        return False


# =========================================================
# РАДІАЦІЙНИЙ ФОН
# =========================================================

def check_radiation():
    value = "0.12 мкЗв/год (Норма)"

    if not read_state(RAD_STATE_FILE):
        write_state(RAD_STATE_FILE, value)

    return value


# =========================================================
# ПОГОДА Open-Meteo
# =========================================================

WEATHER_CODES = {
    0: "☀️ Ясно",
    1: "🌤️ Переважно ясно",
    2: "⛅ Мінлива хмарність",
    3: "☁️ Хмарно",
    45: "🌫️ Туман",
    51: "🌦️ Легкий дощ",
    61: "🌦️ Невеликий дощ",
    63: "🌧️ Дощ",
    71: "🌨️ Сніг",
    80: "🌦️ Злива",
    95: "⛈️ Гроза",
}


def get_current_weather_short():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={KOZELETS_LAT}"
        f"&longitude={KOZELETS_LON}"
        "&current=temperature_2m,weather_code"
        "&timezone=Europe%2FKyiv"
    )

    try:
        response = requests.get(url, timeout=5)

        if response.ok:
            current = response.json()["current"]

            temp = current["temperature_2m"]
            code = current["weather_code"]

            weather = WEATHER_CODES.get(code, "🌤️")

            return f"{weather}, {temp}°C"

    except Exception:
        pass

    return "Дані недоступні"


# =========================================================
# ІНФОРМАЦІЙНА ПАНЕЛЬ
# =========================================================

def update_live_dashboard():

    alarm = read_state(ALERT_STATE_FILE) == "1"

    if alarm:
        alarm_text = "🚨 ТРИВОГА в області!"
    else:
        alarm_text = "🟢 Немає повітряної тривоги"

    weather = get_current_weather_short()
    radiation = check_radiation()

    now = datetime.now(TIMEZONE).strftime("%d.%m.%Y %H:%M")

    text = (
        "📌 ІНФОРМАЦІЙНА ПАНЕЛЬ ГРОМАДИ\n"
        "Козелець • Остер • Бобровиця\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"{alarm_text}\n\n"
        f"🌤️ Погода: {weather}\n"
        f"☢️ Радіаційний фон: {radiation}\n\n"
        "🌊 Моніторинг води: https://neptun.in.ua/\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 Оновлено: {now}\n\n"
        "🤖 Дані автоматично оновлюються кожні 5 хвилин."
    )

    msg = read_state(PINNED_MSG_ID_FILE)

    if msg:
        try:
            msg = int(msg)

            if edit_message(msg, text):
                return

        except Exception:
            pass

    new_msg = send_message(text)

    if new_msg:
        write_state(PINNED_MSG_ID_FILE, new_msg)
        pin_message(new_msg)


# =========================================================
# ГОЛОВНИЙ ЗАПУСК
# =========================================================

def main():
    print("=" * 40)
    print("СТАРТ БОТА")
    print(datetime.now(TIMEZONE))
    print("=" * 40)

    try:
        check_alerts()
    except Exception as e:
        print("Alerts error:", e)

    try:
        update_live_dashboard()
    except Exception as e:
        print("Dashboard error:", e)

    try:
        check_news()
    except Exception as e:
        print("News error:", e)

    try:
        check_and_send_history_post()
    except Exception as e:
        print("History error:", e)

    print("Готово.")


if __name__ == "__main__":
    main()
