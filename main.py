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
# TELEGRAM
# =========================================================

def telegram_url(method):
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def send_message(text):
    """
    Відправляє звичайне повідомлення.
    ВАЖЛИВО:
    disable_web_page_preview=True
    повністю вимикає прев'ю посилань.
    """

    if not BOT_TOKEN or not CHANNEL:
        print("❌ BOT_TOKEN або CHANNEL не задані")
        return False

    # Прибираємо URL із повідомлення
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

        print("Telegram:", response.status_code)

        if response.ok:
            return True

        print("Telegram error:", response.text)

    except Exception as error:
        print("Telegram exception:", error)

    return False


def send_photo(photo_url, caption):
    """
    Публікація новини з фото.
    Посилань у підписі немає.
    """

    if not BOT_TOKEN or not CHANNEL:
        return False

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

        print("Telegram photo:", response.status_code)

        if response.ok:
            return True

        print("Telegram photo error:", response.text)

    except Exception as error:
        print("Telegram photo exception:", error)

    return False


# =========================================================
# ФАЙЛИ СТАНУ
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


# =========================================================
# ОЧИЩЕННЯ ТЕКСТУ
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)

    # прибрати HTML
    text = re.sub(r"<[^>]+>", " ", text)

    # прибрати URL
    text = re.sub(r"https?://\S+", " ", text)

    # зайві пробіли
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_title(title):
    title = clean_text(title)

    # Прибираємо типові закінчення Google News
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


# =========================================================
# GOOGLE NEWS DECODER
# =========================================================

def resolve_news_link(link):

    if not link:
        return link

    if "news.google.com" not in link:
        return link

    if new_decoderv1 is None:
        print("⚠️ googlenewsdecoder не встановлений")
        return link

    try:
        print("🔄 Розшифровую Google News URL...")

        result = new_decoderv1(
            link,
            interval_time=1
        )

        if isinstance(result, dict):

            if result.get("status"):
                decoded_url = result.get("url", "")

                if decoded_url:
                    print("✅ Оригінальна стаття:", decoded_url)
                    return decoded_url

            else:
                print(
                    "⚠️ Google News URL не розшифровано:",
                    result
                )

        elif isinstance(result, str):

            if result.startswith("http"):
                print(
                    "✅ Оригінальна стаття:",
                    result
                )
                return result

    except Exception as error:
        print(
            "Помилка розшифрування Google News:",
            error
        )

    return link


# =========================================================
# ОТРИМАННЯ ТЕКСТУ ТА ФОТО СТАТТІ
# =========================================================

def extract_article_data(url):

    if not url:
        return "", ""

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/140 Safari/537.36"
                )
            },
            timeout=20
        )

        print(
            "Сторінка статті:",
            response.status_code,
            response.url
        )

        if not response.ok:
            return "", ""

        page = response.text

        # -------------------------------------------------
        # ФОТО
        # -------------------------------------------------

        image_url = ""

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']'
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                page,
                flags=re.IGNORECASE
            )

            if match:
                image_url = html.unescape(match.group(1))
                break

        # -------------------------------------------------
        # META DESCRIPTION
        # -------------------------------------------------

        description = ""

        patterns = [
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']'
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                page,
                flags=re.IGNORECASE
            )

            if match:
                description = clean_text(
                    match.group(1)
                )
                break

        # -------------------------------------------------
        # JSON-LD ARTICLEBODY
        # -------------------------------------------------

        article_text = ""

        json_blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            page,
            flags=re.IGNORECASE | re.DOTALL
        )

        for block in json_blocks:

            try:
                data = json.loads(
                    html.unescape(block.strip())
                )

                objects = data if isinstance(data, list) else [data]

                for item in objects:

                    if not isinstance(item, dict):
                        continue

                    body = item.get("articleBody")

                    if body:
                        article_text = clean_text(body)

                        if len(article_text) > 100:
                            break

            except Exception:
                continue

            if len(article_text) > 100:
                break

        if article_text:
            print(
                "Текст статті отримано:",
                len(article_text),
                "символів"
            )
        else:
            print("Текст статті отримано: 0 символів")

        if image_url:
            print("Зображення статті знайдено")
        else:
            print("Зображення статті не знайдено")

        # Не використовуємо величезний текст
        if len(article_text) > 700:
            article_text = article_text[:700].rsplit(" ", 1)[0] + "…"

        if not article_text:
            article_text = description

        return article_text, image_url

    except Exception as error:
        print(
            "Помилка отримання статті:",
            error
        )

    return "", ""


# =========================================================
# RSS GOOGLE NEWS
# =========================================================

def get_google_news(query):

    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}"
        "&hl=uk"
        "&gl=UA"
        "&ceid=UA:uk"
    )

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=20
        )

        print(
            f"Google News [{query}]:",
            response.status_code
        )

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

    except Exception as error:
        print(
            "Google News error:",
            error
        )

    return []


# =========================================================
# ФІЛЬТР НОВИН
# =========================================================

SPORT_WORDS = [
    "футбол",
    "спорт",
    "матч",
    "чемпіонат",
    "баскетбол",
    "теніс",
    "хокей"
]


def is_kozelets_news(title):

    text = title.lower()

    return (
        "козелець" in text
        or "козелецька громада" in text
    )


def is_chernihiv_city_news(title):

    text = title.lower()

    oblast_words = [
        "чернігівщина",
        "чернігівській області",
        "чернігівської області",
        "на чернігівщині",
        "по чернігівщині",
        "чернігівщини",
        "область"
    ]

    if any(
        word in text
        for word in oblast_words
    ):
        return False

    return "чернігів" in text


def is_sport_news(title):

    text = title.lower()

    return any(
        word in text
        for word in SPORT_WORDS
    )


# =========================================================
# ДЕДУПЛІКАЦІЯ
# =========================================================

def normalize_title(title):

    title = title.lower()

    title = re.sub(
        r"[^а-яіїєґa-z0-9 ]",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


def similar_titles(title1, title2):

    a = set(normalize_title(title1).split())
    b = set(normalize_title(title2).split())

    if not a or not b:
        return False

    intersection = len(a & b)
    smaller = min(len(a), len(b))

    return (
        smaller > 4
        and intersection / smaller >= 0.65
    )


def make_news_id(title):

    normalized = normalize_title(title)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def load_seen_news():

    content = read_state(
        NEWS_STATE_FILE
    )

    if not content:
        return set()

    return set(
        line.strip()
        for line in content.splitlines()
        if line.strip()
    )


def save_seen_news(seen):

    # Не дозволяємо файлу ставати нескінченним
    last_items = list(seen)[-1000:]

    try:
        with open(
            NEWS_STATE_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            for item in last_items:
                file.write(item + "\n")

    except Exception as error:
        print(
            "Помилка збереження новин:",
            error
        )


# =========================================================
# ПЕРЕВІРКА НОВИН
# =========================================================

def check_news():

    seen = load_seen_news()

    prepared = []

    for source in NEWS_SOURCES:

        items = get_google_news(
            source["query"]
        )

        for item in items:

            title = item["title"]

            if not title:
                continue

            # Не беремо старі новини
            now = datetime.now(TIMEZONE)

            try:
                item_date = item["date"].astimezone(
                    TIMEZONE
                )
            except Exception:
                item_date = now

            age_hours = (
                now - item_date
            ).total_seconds() / 3600

            if age_hours > 3:
                continue

            if age_hours < -1:
                continue

            category = source["category"]

            # -------------------------------------------------
            # КОЗЕЛЕЦЬ
            # -------------------------------------------------

            if category == "📍 КОЗЕЛЕЦЬ":

                if not is_kozelets_news(title):
                    continue

            # -------------------------------------------------
            # ЧЕРНІГІВ
            # -------------------------------------------------

            elif category == "🏙️ ЧЕРНІГІВ":

                if not is_chernihiv_city_news(title):
                    continue

            # -------------------------------------------------
            # СПОРТ НЕ ПУБЛІКУЄМО В МІСЦЕВИХ
            # -------------------------------------------------

            if category in [
                "📍 КОЗЕЛЕЦЬ",
                "🏙️ ЧЕРНІГІВ",
                "🏙️ ЧЕРНІГІВЩИНА"
            ]:

                if is_sport_news(title):
                    continue

            news_id = make_news_id(title)

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

    # ---------------------------------------------------------
    # СОРТУВАННЯ:
    # СПОЧАТКУ ВИЩИЙ ПРІОРИТЕТ,
    # ПОТІМ НОВІШІ
    # ---------------------------------------------------------

    prepared.sort(
        key=lambda item: (
            item["priority"],
            -item["date"].timestamp()
        )
    )

    # ---------------------------------------------------------
    # ПРИБИРАЄМО ДУБЛІ МІЖ ДЖЕРЕЛАМИ
    # ---------------------------------------------------------

    unique_news = []

    for item in prepared:

        duplicate = False

        for existing in unique_news:

            if similar_titles(
                item["title"],
                existing["title"]
            ):
                duplicate = True
                break

        if not duplicate:
            unique_news.append(item)

    published = 0

    for item in unique_news:

        print(
            "\nПеревірка:",
            item["title"],
            "| пріоритет:",
            item["priority"]
        )

        original_url = resolve_news_link(
            item["link"]
        )

        article_text, image_url = extract_article_data(
            original_url
        )

        if not article_text:
            article_text = (
                item["description"]
                if item["description"]
                else "Подробиці новини уточнюються."
            )

        # Прибираємо типові рекламні/службові фрази
        article_text = clean_text(
            article_text
        )

        # -----------------------------------------------------
        # ФОРМУЄМО ПОВІДОМЛЕННЯ
        # -----------------------------------------------------

        caption = (
            f"{item['category']}\n\n"
            f"📰 {item['title']}\n\n"
            f"{article_text}"
        )

        # Ніяких URL у Telegram
        caption = re.sub(
            r"https?://\S+",
            "",
            caption
        ).strip()

        success = False

        if image_url:

            success = send_photo(
                image_url,
                caption
            )

        if not success:

            success = send_message(
                caption
            )

        if success:

            seen.add(
                item["id"]
            )

            published += 1

            print(
                "✅ Опубліковано:",
                item["title"]
            )

        else:

            print(
                "❌ Не вдалося опублікувати:",
                item["title"]
            )

    save_seen_news(seen)

    print(
        "\nНових новин опубліковано:",
        published
    )


# =========================================================
# NEPTUN
# =========================================================

def region_is_active(region):

    if not isinstance(region, dict):
        return False

    for key in [
        "active",
        "is_active",
        "alarm",
        "alert"
    ]:

        value = region.get(key)

        if value is True:
            return True

    status = str(
        region.get(
            "status",
            ""
        )
    ).lower()

    return status in [
        "active",
        "alarm",
        "alert",
        "on"
    ]


def find_neptun_region(data, words):

    if isinstance(data, dict):

        name = str(
            data.get(
                "name",
                data.get(
                    "title",
                    data.get(
                        "region",
                        ""
                    )
                )
            )
        ).lower()

        if any(
            word in name
            for word in words
        ):

            return region_is_active(
                data
            )

        for value in data.values():

            result = find_neptun_region(
                value,
                words
            )

            if result:
                return True

    elif isinstance(data, list):

        for item in data:

            result = find_neptun_region(
                item,
                words
            )

            if result:
                return True

    return False


def check_neptun():

    url = "https://neptun.in.ua/api/v1/alerts"

    try:

        response = requests.get(
            url,
            timeout=20
        )

        print(
            "NEPTUN API:",
            response.status_code
        )

        if not response.ok:
            return

        data = response.json()

        oblast_active = find_neptun_region(
            data,
            [
                "чернігівська область",
                "чернігівщина"
            ]
        )

        raion_active = find_neptun_region(
            data,
            [
                "чернігівський район"
            ]
        )

        active = (
            oblast_active
            or raion_active
        )

        print(
            "Чернігівська область активна:",
            oblast_active
        )

        print(
            "Чернігівський район активна:",
            raion_active
        )

        old_state = (
            read_state(
                ALERT_STATE_FILE
            )
            == "1"
        )

        # -----------------------------------------------------
        # ПОЧАТОК ТРИВОГИ
        # -----------------------------------------------------

        if active and not old_state:

            message = (
                "🚨 ПОВІТРЯНА ТРИВОГА\n\n"
                "Чернігівська область / "
                "Чернігівський район\n\n"
                "⚠️ Перейдіть в укриття!"
            )

            if send_message(message):

                write_state(
                    ALERT_STATE_FILE,
                    "1"
                )

        # -----------------------------------------------------
        # ВІДБІЙ
        # -----------------------------------------------------

        elif not active and old_state:

            message = (
                "🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
                "За даними системи моніторингу "
                "активна тривога завершена."
            )

            if send_message(message):

                write_state(
                    ALERT_STATE_FILE,
                    "0"
                )

    except Exception as error:

        print(
            "NEPTUN error:",
            error
        )


# =========================================================
# MAPA.UA
# =========================================================

def check_mapa():

    url = (
        "https://mapa.ua/api/v1/nearby"
        f"?lat={KOZELETS_LAT}"
        f"&lon={KOZELETS_LON}"
        f"&radius_km={MAPA_RADIUS_KM}"
    )

    try:

        response = requests.get(
            url,
            timeout=20
        )

        print(
            "MAPA.UA API:",
            response.status_code
        )

        if not response.ok:
            return

        data = response.json()

        threats = data.get(
            "threats",
            []
        )

        active_threats = []

        for threat in threats:

            if not isinstance(
                threat,
                dict
            ):
                continue

            status = str(
                threat.get(
                    "status",
                    ""
                )
            ).lower()

            if status != "active":
                continue

            # Беремо тільки тип і відстань.
            # Координати та маршрути НЕ публікуємо.
            kind = str(
                threat.get(
                    "kind",
                    "невідома загроза"
                )
            )

            distance = threat.get(
                "distance_km"
            )

            try:
                distance_value = round(
                    float(distance),
                    1
                )
            except Exception:
                distance_value = None

            threat_id = str(
                threat.get(
                    "id",
                    ""
                )
            )

            active_threats.append({
                "id": threat_id,
                "kind": kind,
                "distance": distance_value
            })

        print(
            "MAPA.UA: активних загроз:",
            len(active_threats)
        )

        # -----------------------------------------------------
        # УНІКАЛЬНИЙ СТАН
        # -----------------------------------------------------

        signatures = []

        for threat in active_threats:

            signatures.append(
                "|".join([
                    threat["id"],
                    threat["kind"],
                    str(threat["distance"])
                ])
            )

        signatures.sort()

        new_state = "\n".join(
            signatures
        )

        old_state = read_state(
            MAPA_STATE_FILE
        )

        # -----------------------------------------------------
        # З'ЯВИЛАСЯ НОВА ЗАГРОЗА
        # -----------------------------------------------------

        if active_threats and new_state != old_state:

            message = (
                "⚠️ ДОДАТКОВЕ ПОПЕРЕДЖЕННЯ\n\n"
                "MAPA.UA фіксує активну "
                "повітряну загрозу поблизу Козельця.\n\n"
                "Це додаткова інформація "
                "до офіційних повідомлень про повітряну тривогу.\n\n"
                "‼️ У разі оголошення офіційної "
                "повітряної тривоги негайно прямуйте "
                "до укриття."
            )

            # ВАЖЛИВО:
            # Тут НЕМАЄ посилання на MAPA.UA
            # і Telegram не створить прев'ю.

            if send_message(message):

                write_state(
                    MAPA_STATE_FILE,
                    new_state
                )

        # -----------------------------------------------------
        # ЗАГРОЗ БІЛЬШЕ НЕМАЄ
        # -----------------------------------------------------

        elif not active_threats and old_state:

            message = (
                "🟢 ДОДАТКОВЕ ПОПЕРЕДЖЕННЯ ЗАВЕРШЕНО\n\n"
                "Активних загроз поблизу Козельця "
                "за даними додаткового моніторингу "
                "не зафіксовано."
            )

            if send_message(message):

                write_state(
                    MAPA_STATE_FILE,
                    ""
                )

    except Exception as error:

        print(
            "MAPA.UA error:",
            error
        )


# =========================================================
# ПОГОДА
# =========================================================

WEATHER_CODES = {
    0: "☀️ Ясно",
    1: "🌤️ Переважно ясно",
    2: "⛅ Мінлива хмарність",
    3: "☁️ Хмарно",
    45: "🌫️ Туман",
    48: "🌫️ Туман",
    51: "🌦️ Легкий дощ",
    53: "🌦️ Дощ",
    55: "🌧️ Сильний дощ",
    61: "🌦️ Невеликий дощ",
    63: "🌧️ Дощ",
    65: "🌧️ Сильний дощ",
    71: "🌨️ Невеликий сніг",
    73: "🌨️ Сніг",
    75: "❄️ Сильний сніг",
    80: "🌦️ Короткочасний дощ",
    81: "🌧️ Зливи",
    82: "🌧️ Сильні зливи",
    95: "⛈️ Гроза",
    96: "⛈️ Гроза з градом",
    99: "⛈️ Сильна гроза з градом"
}


def get_weather(
    lat,
    lon,
    name,
    date_text
):

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}"
        f"&longitude={lon}"
        "&daily="
        "weather_code,"
        "temperature_2m_max,"
        "temperature_2m_min,"
        "precipitation_probability_max,"
        "precipitation_sum,"
        "wind_speed_10m_max,"
        "sunrise,"
        "sunset"
        "&timezone=Europe%2FKyiv"
        "&forecast_days=2"
    )

    try:

        response = requests.get(
            url,
            timeout=20
        )

        if not response.ok:
            return ""

        data = response.json()

        daily = data.get(
            "daily",
            {}
        )

        dates = daily.get(
            "time",
            []
        )

        if date_text not in dates:
            return ""

        index = dates.index(
            date_text
        )

        code = daily[
            "weather_code"
        ][index]

        description = WEATHER_CODES.get(
            code,
            "🌤️ Змінна погода"
        )

        t_min = daily[
            "temperature_2m_min"
        ][index]

        t_max = daily[
            "temperature_2m_max"
        ][index]

        rain_probability = daily[
            "precipitation_probability_max"
        ][index]

        rain_amount = daily[
            "precipitation_sum"
        ][index]

        wind = daily[
            "wind_speed_10m_max"
        ][index]

        sunrise = daily[
            "sunrise"
        ][index]

        sunset = daily[
            "sunset"
        ][index]

        sunrise_time = (
            sunrise.split("T")[-1][:5]
        )

        sunset_time = (
            sunset.split("T")[-1][:5]
        )

        return (
            f"{name}\n"
            f"{description}\n"
            f"🌡️ {t_min}°C ... {t_max}°C\n"
            f"🌧️ Ймовірність опадів: "
            f"{rain_probability}%\n"
            f"💧 Опади: {rain_amount} мм\n"
            f"💨 Максимальний вітер: "
            f"{wind} км/год\n"
            f"🌅 Схід сонця: {sunrise_time}\n"
            f"🌇 Захід сонця: {sunset_time}"
        )

    except Exception as error:

        print(
            "Weather error:",
            error
        )

    return ""


def check_weather():

    now = datetime.now(
        TIMEZONE
    )

    hour = now.hour

    # Працюємо тільки о 08:00 та 20:00
    if hour not in [
        8,
        20
    ]:
        return

    today = now.strftime(
        "%Y-%m-%d"
    )

    if hour == 8:

        forecast_date = today

        title = (
            "🌤️ ПОГОДА НА СЬОГОДНІ"
        )

        state_key = (
            f"{today}_morning"
        )

    else:

        tomorrow = (
            now.date()
            .fromordinal(
                now.date().toordinal() + 1
            )
        )

        forecast_date = tomorrow.strftime(
            "%Y-%m-%d"
        )

        title = (
            "🌤️ ПОГОДА НА ЗАВТРА"
        )

        state_key = (
            f"{today}_evening"
        )

    old_state = read_state(
        WEATHER_STATE_FILE
    )

    if old_state == state_key:
        return

    kozelets = get_weather(
        KOZELETS_LAT,
        KOZELETS_LON,
        "📍 КОЗЕЛЕЦЬ",
        forecast_date
    )

    chernihiv = get_weather(
        CHERNIHIV_LAT,
        CHERNIHIV_LON,
        "🏙️ ЧЕРНІГІВ",
        forecast_date
    )

    if not kozelets and not chernihiv:
        return

    message_parts = [
        title,
        ""
    ]

    if kozelets:
        message_parts.append(
            kozelets
        )
        message_parts.append("")

    if chernihiv:
        message_parts.append(
            chernihiv
        )

    message = "\n".join(
        message_parts
    )

    if send_message(message):

        write_state(
            WEATHER_STATE_FILE,
            state_key
        )


# =========================================================
# ОСНОВНИЙ ЗАПУСК
# =========================================================

def main():

    print(
        "\n=== Перевірка Козелець Alarm ===\n"
    )

    if not BOT_TOKEN:
        print(
            "❌ BOT_TOKEN не знайдено"
        )
        return

    if not CHANNEL:
        print(
            "❌ CHANNEL не знайдено"
        )
        return

    # Новини
    check_news()

    # Офіційна система тривог
    check_neptun()

    # Додатковий моніторинг
    check_mapa()

    # Погода
    check_weather()

    print(
        "\n=== Перевірку завершено ===\n"
    )


if __name__ == "__main__":
    main()
