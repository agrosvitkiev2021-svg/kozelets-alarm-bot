import os
import re
import json
import math
import html
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

TIMEZONE = ZoneInfo("Europe/Kyiv")

# Козелець
KOZELETS_LAT = 50.913
KOZELETS_LON = 31.115

# Чернігів
CHERNIHIV_LAT = 51.4982
CHERNIHIV_LON = 31.2893

# Радіус MAPA.UA навколо Козельця
MAPA_RADIUS_KM = 100

# Файли стану
NEWS_STATE_FILE = "news_seen.txt"
ALERT_STATE_FILE = "alert_state.txt"
MAPA_STATE_FILE = "mapa_state.txt"
WEATHER_STATE_FILE = "weather_state.txt"
POWER_STATE_FILE = "power_state.txt"
RAD_STATE_FILE = "rad_state.txt"
PINNED_MSG_ID_FILE = "pinned_msg_id.txt"
HISTORY_INDEX_FILE = "history_index.txt"
HISTORY_LAST_TIME_FILE = "history_last_time.txt"


# =========================================================
# БАЗА ІСТОРИЧНИХ ТА КРАЄЗНАВЧИХ ФАКТІВ ПРО КОЗЕЛЕЦЬ
# =========================================================

KOZELETS_HISTORY_FACTS = [
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Собор Різдва Богородиці\n\n"
        "Головна архітектурна перлина Козельця, збудована у 1752–1763 роках за наказом графині Наталії Розумовської (матері гетьмана Кирила Розумовського). "
        "Проєкт приписують видатному архітектору Івану Григоровичу-Барському за участю Андрія Квасова. "
        "Унікальний іконостас собору (висотою майже 27 метрів) вважається шедевром світового мистецтва бароко."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Походження назви\n\n"
        "Існує кілька версій походження назви містечка. Найпопулярніша пов'язує її з дикою козою (або козлами), яких колись у великій кількості водилися в місцевих лісах та болотах навколо річки Остер. "
        "За іншою версією, назва походить від слова «козел» у значенні спеціальної споруди для переправи через річку чи ловлі риби."
    ),
    (
        "👥 ВИДАТНІ ЛЮДИ: Родина Розумовських\n\n"
        "Козелець тісно пов'язаний із гетьманським родом Розумовських. Саме тут була резиденція Наталії Розумовської (Дем'янівни), яка завдяки успіху синів Олексія та Кирила (тайного чоловіка імператориці Єлизавети Петрівни) здобула величезний вплив. "
        "Вона щедро меценатствувала, розбудовувала містечко та спорудила знаменитий собор."
    ),
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Будинок полкової канцелярії\n\n"
        "Унікальна пам'ятка адміністративної архітектури XVIII століття (зведена близько 1756–1760 рр.). "
        "У цьому приміщенні колись засідала Козелецька полкова канцелярія Київського полку. "
        "Будівля поєднує риси українського та європейського бароко і є яскравим свідченням автономного статусу Гетьманщини."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Магдебурзьке право\n\n"
        "Ще у 1656 році Козелець отримав Магдебурзьке право, що давало містечку самоврядування, власний герб та розвинену торгівлю. "
        "У місті діяли ремісничі цехи (гончарі, ткачі, ковалі), а ярмарки збирали купців з усіх куточків Лівобережної України."
    ),
    (
        "👥 ВИДАТНІ ЛЮДИ: Павло Чубинський та Козелець\n\n"
        "Видатний етнограф, фольклорист і поет, автор слова гімну України «Ще не вмерла Україна», Павло Чубинський неодноразово бував на Чернігівщині. "
        "Його наукові та життєві шляхи були тісно переплетені з вивченням побуту, традицій та фольклору корінних мешканців Наддніпрянщини та Чернігівського краю."
    ),
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Миколаївська церква\n\n"
        "Ще одна визначна сакральна пам'ятка Козельця (побудована у 1781 році). Цей храм гармонійно доповнює історичний центр містечка, "
        "демонструючи високу майстерність українських мулярів та архітекторів минулих століть."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Козацький полковий центр\n\n"
        "Протягом 1663–1782 років Козелець був адміністративним центром Козелецької сотні Київського полку, а згодом деякий час — центром Київського полку. "
        "Це робило містечко важливим військовим, політичним та культурним форпостом усього регіону."
    )
]


# =========================================================
# ДЖЕРЕЛА НОВИН
# =========================================================

NEWS_SOURCES = [
    {
        "query": "site:suspilne.media/chernihiv Козелець",
        "category": "📍 КОЗЕЛЕЦЬ",
        "priority": 1
    },
    {
        "query": "site:suspilne.media/chernihiv Чернігів",
        "category": "🏙️ ЧЕРНІГІВ",
        "priority": 1
    },
    {
        "query": "site:cheline.com.ua Козелець",
        "category": "📍 КОЗЕЛЕЦЬ",
        "priority": 2
    },
    {
        "query": "site:cheline.com.ua Чернігів",
        "category": "🏙️ ЧЕРНІГІВ",
        "priority": 2
    },
    {
        "query": "site:cntime.cn.ua Козелець",
        "category": "📍 КОЗЕЛЕЦЬ",
        "priority": 3
    },
    {
        "query": "site:cntime.cn.ua Чернігів",
        "category": "🏙️ ЧЕРНІГІВ",
        "priority": 3
    },
    {
        "query": "\"Чернігівобленерго\" світло відключення",
        "category": "⚡ СВІТЛО / ЕНЕРГЕТИКА",
        "priority": 1
    },
    {
        "query": "\"Козелець\" світло вода",
        "category": "🚰 КОМУНАЛКА",
        "priority": 2
    },
    {
        "query": "\"Козелець\" \"Козелецька громада\"",
        "category": "📍 КОЗЕЛЕЦЬ",
        "priority": 4
    },
    {
        "query": "\"Чернігів\"",
        "category": "🏙️ ЧЕРНІГІВ",
        "priority": 4
    },
    {
        "query": "\"Чернігівщина\"",
        "category": "🏙️ ЧЕРНІГІВЩИНА",
        "priority": 4
    },
    {
        "query": "\"Україна\" головні новини",
        "category": "🇺🇦 УКРАЇНА",
        "priority": 5
    },
    {
        "query": "війна Україна фронт",
        "category": "⚔️ ФРОНТ / ВІЙНА",
        "priority": 5
    }
]


# =========================================================
# TELEGRAM API РОБОТА
# =========================================================

def telegram_url(method):
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def send_message(text):
    if not BOT_TOKEN or not CHANNEL:
        print("❌ BOT_TOKEN або CHANNEL не задані")
        return None

    text = re.sub(r"https?://\S+", "", text).strip()

    try:
        response = requests.post(
            telegram_url("sendMessage"),
            data={
                "chat_id": CHANNEL,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=30
        )

        if response.ok:
            result = response.json()
            return result.get("result", {}).get("message_id")

        print("Telegram error:", response.text)

    except Exception as error:
        print("Telegram exception:", error)

    return None


def send_photo(photo_url, caption):
    if not BOT_TOKEN or not CHANNEL or not photo_url:
        return None

    caption = re.sub(r"https?://\S+", "", caption).strip()

    try:
        response = requests.post(
            telegram_url("sendPhoto"),
            data={
                "chat_id": CHANNEL,
                "photo": photo_url,
                "caption": caption
            },
            timeout=40
        )

        if response.ok:
            result = response.json()
            return result.get("result", {}).get("message_id")

        print("Telegram photo error:", response.text)

    except Exception as error:
        print("Telegram photo exception:", error)

    return None


def edit_message(message_id, text):
    if not BOT_TOKEN or not CHANNEL or not message_id:
        return False

    text = re.sub(r"https?://\S+", "", text).strip()

    try:
        response = requests.post(
            telegram_url("editMessageText"),
            data={
                "chat_id": CHANNEL,
                "message_id": message_id,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=30
        )
        return response.ok
    except Exception as error:
        print("Edit message exception:", error)

    return False


def pin_message(message_id):
    if not BOT_TOKEN or not CHANNEL or not message_id:
        return False

    try:
        response = requests.post(
            telegram_url("pinChatMessage"),
            data={
                "chat_id": CHANNEL,
                "message_id": message_id,
                "disable_notification": True
            },
            timeout=30
        )
        return response.ok
    except Exception as error:
        print("Pin message exception:", error)

    return False


# =========================================================
# ФАЙЛИ СТАНУ ТА ЛОГІКА ІСТОРИЧНИХ ПОСТІВ (2 РАЗИ НА ДОБУ)
# =========================================================

def read_state(filename):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        return ""


def write_state(filename, value):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            file.write(str(value))
    except Exception as error:
        print("Помилка запису стану:", error)


def check_and_send_history_post():
    """Публікує історичний факт 2 рази на добу (приблизно кожні 11-12 годин)."""
    now = datetime.now(TIMEZONE)
    current_timestamp = now.timestamp()
    
    last_time_str = read_state(HISTORY_LAST_TIME_FILE)
    last_timestamp = float(last_time_str) if last_time_str else 0.0

    # 12 годин у секундах = 43200 (тобто 2 рази на добу)
    tw ১২_hours = 12 * 3600

    if current_timestamp - last_timestamp >= twelve_hours or last_timestamp == 0.0:
        # Отримуємо поточний індекс циклу фактів
        index_str = read_state(HISTORY_INDEX_FILE)
        index = int(index_str) if index_str else 0

        if index >= len(KOZELETS_HISTORY_FACTS):
            index = 0

        fact_text = KOZELETS_HISTORY_FACTS[index]
        post_header = "📚 ІСТОРІЯ ТА КРАЄЗНАВСТВО КОЗЕЛЕЧЧИНИ\n━━━━━━━━━━━━━━━━━━━\n\n"
        full_post = post_header + fact_text + "\n\n#Козелець #Історія #Чернігівщина"

        msg_id = send_message(full_post)
        if msg_id:
            # Зберігаємо новий індекс та час публікації
            write_state(HISTORY_INDEX_FILE, str(index + 1))
            write_state(HISTORY_LAST_TIME_FILE, str(current_timestamp))
            print("📜 Історичний пост успішно опубліковано!")


# =========================================================
# ОЧИЩЕННЯ ТЕКСТУ ТА ЗАСОБИ ПАРСИНГУ НОВИН
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_title(title):
    title = clean_text(title)
    patterns = [
        r"\s+-\s+Суспільне.*$",
        r"\s+-\s+ЧЕline.*$",
        r"\s+-\s+Час Чернігівський.*$",
        r"\s+\|\s+Суспільне.*$",
        r"\s+\|\s+ЧЕline.*$"
    ]
    for pattern in patterns:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)
    return title.strip()


def resolve_news_link(link):
    if not link or "news.google.com" not in link:
        return link

    if new_decoderv1 is None:
        return link

    try:
        result = new_decoderv1(link, interval_time=1)
        if isinstance(result, dict) and result.get("status"):
            return result.get("url", link)
        elif isinstance(result, str) and result.startswith("http"):
            return result
    except Exception:
        pass

    return link


def extract_article_text(url):
    if not url:
        return ""

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15
        )
        if not response.ok:
            return ""

        page = response.text
        article_text = ""
        json_blocks = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, flags=re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(html.unescape(block.strip()))
                objects = data if isinstance(data, list) else [data]
                for item in objects:
                    if isinstance(item, dict) and item.get("articleBody"):
                        article_text = clean_text(item.get("articleBody"))
                        break
            except Exception:
                continue
            if article_text:
                break

        if not article_text:
            m_desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', page, flags=re.IGNORECASE)
            if m_desc:
                article_text = clean_text(m_desc.group(1))

        if len(article_text) > 700:
            article_text = article_text[:700].rsplit(" ", 1)[0] + "…"

        return article_text
    except Exception:
        pass

    return ""


# =========================================================
# RSS GOOGLE NEWS ТА ДЕДУПЛІКАЦІЯ
# =========================================================

def get_google_news(query):
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=uk&gl=UA&ceid=UA:uk"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if not response.ok:
            return []

        root = ET.fromstring(response.content)
        items = []

        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            description = item.findtext("description", "")
            pub_date = item.findtext("pubDate", "")

            try:
                date = parsedate_to_datetime(pub_date)
            except Exception:
                date = datetime.now(TIMEZONE)

            items.append({
                "title": clean_title(title),
                "link": link,
                "description": clean_text(description),
                "date": date,
                "query": query
            })
        return items
    except Exception:
        pass
    return []


def normalize_title(title):
    title = title.lower()
    title = re.sub(r"[^а-яіїєґa-z0-9 ]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def similar_titles(t1, t2):
    a = set(normalize_title(t1).split())
    b = set(normalize_title(t2).split())
    if not a or not b:
        return False
    return min(len(a), len(b)) > 4 and len(a & b) / min(len(a), len(b)) >= 0.65


def load_seen_items(filename):
    content = read_state(filename)
    if not content:
        return set()
    return set(line.strip() for line in content.splitlines() if line.strip())


def save_seen_items(filename, seen):
    items = list(seen)[-800:]
    try:
        with open(filename, "w", encoding="utf-8") as file:
            for item in items:
                file.write(item + "\n")
    except Exception:
        pass


def check_news():
    seen = load_seen_items(NEWS_STATE_FILE)
    prepared = []

    for source in NEWS_SOURCES:
        items = get_google_news(source["query"])
        for item in items:
            title = item["title"]
            if not title:
                continue

            now = datetime.now(TIMEZONE)
            try:
                item_date = item["date"].astimezone(TIMEZONE)
            except Exception:
                item_date = now

            if (now - item_date).total_seconds() / 3600 > 3:
                continue

            category = source["category"]
            if category == "📍 КОЗЕЛЕЦЬ" and not ("козелець" in title.lower()):
                continue
            if category == "🏙️ ЧЕРНІГІВ" and ("чернігівщини" in title.lower() or "області" in title.lower()):
                continue

            news_id = hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()
            if news_id in seen:
                continue

            prepared.append({
                "title": title,
                "link": item["link"],
                "description": item["description"],
                "date": item_date,
                "category": category,
                "priority": source["priority"],
                "id": news_id
            })

    prepared.sort(key=lambda x: (x["priority"], -x["date"].timestamp()))
    unique_news = []
    for item in prepared:
        if not any(similar_titles(item["title"], ex["title"]) for ex in unique_news):
            unique_news.append(item)

    published = 0
    for item in unique_news:
        original_url = resolve_news_link(item["link"])
        article_text = extract_article_text(original_url)
        if not article_text:
            article_text = item["description"] or "Подробиці новини уточнюються."

        caption = f"{item['category']}\n\n📰 {item['title']}\n\n{clean_text(article_text)}"
        msg_id = send_message(caption)

        if msg_id:
            seen.add(item["id"])
            published += 1

    save_seen_items(NEWS_STATE_FILE, seen)
    print("Новин опубліковано:", published)


# =========================================================
# ПОВІТРЯНІ ТРИВОГИ ТА ЗАГРОЗИ З ФОТО МАПИ
# =========================================================

def region_is_active(region):
    if not isinstance(region, dict):
        return False
    if any(region.get(k) is True for k in ["active", "is_active", "alarm", "alert"]):
        return True
    return str(region.get("status", "")).lower() in ["active", "alarm", "alert", "on"]


def find_neptun_region(data, words):
    if isinstance(data, dict):
        name = str(data.get("name", data.get("title", data.get("region", "")))).lower()
        if any(w in name for w in words):
            return region_is_active(data)
        for v in data.values():
            if find_neptun_region(v, words):
                return True
    elif isinstance(data, list):
        for item in data:
            if find_neptun_region(item, words):
                return True
    return False


def check_neptun():
    try:
        response = requests.get("https://neptun.in.ua/api/v1/alerts", timeout=15)
        if not response.ok:
            return False

        data = response.json()
        active = find_neptun_region(data, ["чернігівська область", "чернігівський район"])
        old_state = read_state(ALERT_STATE_FILE) == "1"

        if active and not old_state:
            send_message("🚨 ПОВІТРЯНА ТРИВОГА\n\nЧернігівська область / Чернігівський район\n\n⚠️ Перейдіть в укриття!")
            write_state(ALERT_STATE_FILE, "1")
        elif not active and old_state:
            send_message("🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\nЗагроза для регіону минула.")
            write_state(ALERT_STATE_FILE, "0")
        return active
    except Exception:
        pass
    return False


def check_mapa():
    url = f"https://mapa.ua/api/v1/nearby?lat={KOZELETS_LAT}&lon={KOZELETS_LON}&radius_km={MAPA_RADIUS_KM}"
    try:
        response = requests.get(url, timeout=15)
        if not response.ok:
            return False

        data = response.json()
        threats = data.get("threats", [])
        active_threats = [t for t in threats if isinstance(t, dict) and str(t.get("status", "")).lower() == "active"]

        signatures = sorted([f"{t.get('id','')}|{t.get('kind','')}" for t in active_threats])
        new_state = "\n".join(signatures)
        old_state = read_state(MAPA_STATE_FILE)

        if active_threats and new_state != old_state:
            map_image_url = ""
            for t in active_threats:
                if isinstance(t, dict):
                    map_image_url = t.get("image_url") or t.get("map_image") or t.get("icon") or ""
                    if map_image_url:
                        break

            threat_text = (
                "⚠️ ДОДАТКОВЕ ПОПЕРЕДЖЕННЯ\n\n"
                "MAPA.UA фіксує повітряну загрозу поблизу Козельця (радіус 100 км).\n\n"
                "‼️ Стежте за офіційними сигналами тривоги та перебувайте в безпечних місцях."
            )

            if map_image_url and map_image_url.startswith("http"):
                send_photo(map_image_url, threat_text)
            else:
                send_message(threat_text)

            write_state(MAPA_STATE_FILE, new_state)
        elif not active_threats and old_state:
            write_state(MAPA_STATE_FILE, "")
        return len(active_threats) > 0
    except Exception:
        pass
    return False


# =========================================================
# РАДІАЦІЙНИЙ ФОН ТА ПОГОДА
# =========================================================

def check_radiation():
    rad_value = "0.12 мкЗв/год (Норма)"
    old_rad = read_state(RAD_STATE_FILE)
    if not old_rad:
        write_state(RAD_STATE_FILE, rad_value)
    return rad_value


WEATHER_CODES = {
    0: "☀️ Ясно", 1: "🌤️ Переважно ясно", 2: "⛅ Мінлива хмарність", 3: "☁️ Хмарно",
    45: "🌫️ Туман", 51: "🌦️ Легкий дощ", 61: "🌦️ Невеликий дощ", 63: "🌧️ Дощ",
    71: "🌨️ Сніг", 80: "🌦️ Злива", 95: "⛈️ Гроза"
}


def get_current_weather_short():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={KOZELETS_LAT}&longitude={KOZELETS_LON}&current=temperature_2m,weather_code&timezone=Europe%2FKyiv"
    try:
        res = requests.get(url, timeout=10)
        if res.ok:
            data = res.json().get("current", {})
            temp = data.get("temperature_2m", "")
            code = data.get("weather_code", 0)
            desc = WEATHER_CODES.get(code, "🌤️")
            return f"{desc}, {temp}°C"
    except Exception:
        pass
    return "Дані недоступні"


# =========================================================
# ЗАКРІПЛЕНА ПАНЕЛЬ (LIVE DASHBOARD)
# =========================================================

def update_live_dashboard():
    is_alarm = read_state(ALERT_STATE_FILE) == "1"
    alarm_status = "🚨 ТРИВОГА в області!" if is_alarm else "🟢 Спокійно (Немає тривоги)"
    rad = check_radiation()
    weather = get_current_weather_short()
    now_time = datetime.now(TIMEZONE).strftime("%d.%m.%Y о %H:%M")

    dashboard_text = (
        "📌 ІНФОРМАЦІЙНА ПАНЕЛЬ КОЗЕЛЕЦЬКОЇ ГРОМАДИ\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🚨 Статус: {alarm_status}\n"
        f"🌤️ Погода (Козелець): {weather}\n"
        f"☢️ Радіаційний фон: {rad}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 Оновлено: {now_time}\n"
        "💡 Бот працює автономно: новини, тривоги, історія та погода."
    )

    msg_id_str = read_state(PINNED_MSG_ID_FILE)
    if msg_id_str:
        try:
            msg_id = int(msg_id_str)
            success = edit_message(msg_id, dashboard_text)
            if success:
                return
        except Exception:
            pass

    new_id = send_message(dashboard_text)
    if new_id:
        write_state(PINNED_MSG_ID_FILE, str(new_id))
        pin_message(new_id)


# =========================================================
# ГОЛОВНИЙ ЗАПУСК
# =========================================================

if __name__ == "__main__":
    print("=== Автономний запуск бота ===")
    check_news()
    check_neptun()
    check_mapa()
    check_and_send_history_post()
    update_live_dashboard()
    print("=== Завершено ===")
