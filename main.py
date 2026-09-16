import os
import html
import re
import json
import hashlib
import requests
import xml.etree.ElementTree as ET

from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None


BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = os.environ.get("CHANNEL", "@Kozelets_Alarm")

NEWS_SEEN_FILE = "news_seen.txt"
ALERT_STATE_FILE = "alert_state.txt"
MAPA_STATE_FILE = "mapa_state.txt"
WEATHER_STATE_FILE = "weather_state.txt"

MAX_NEWS_AGE_HOURS = 3

KOZELETS_LAT = 50.913
KOZELETS_LON = 31.115

CHERNIHIV_LAT = 51.4982
CHERNIHIV_LON = 31.2893

MAPA_RADIUS_KM = 100

KYIV_TZ = ZoneInfo("Europe/Kyiv")


# ============================================================
# НАЛАШТУВАННЯ ДЖЕРЕЛ
# ============================================================

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


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text):

    if not BOT_TOKEN:
        print("Помилка: BOT_TOKEN не заданий")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:

        response = requests.post(
            url,
            json={
                "chat_id": CHANNEL,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=20
        )

        print("Telegram:", response.status_code)

        if not response.ok:
            print("Помилка Telegram:", response.text)

        return response.ok

    except Exception as error:

        print("Помилка Telegram:", error)

        return False


def send_telegram_photo(photo_url, caption):

    if not BOT_TOKEN:
        print("Помилка: BOT_TOKEN не заданий")
        return False

    try:

        image_response = requests.get(
            photo_url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        if not image_response.ok:

            print(
                "Не вдалося завантажити зображення:",
                image_response.status_code
            )

            return False

        content_type = image_response.headers.get(
            "Content-Type",
            "image/jpeg"
        )

        if not content_type.startswith("image/"):

            print(
                "Посилання не є зображенням:",
                content_type
            )

            return False

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

        response = requests.post(
            url,
            data={
                "chat_id": CHANNEL,
                "caption": caption[:1024]
            },
            files={
                "photo": (
                    "image.jpg",
                    image_response.content,
                    content_type
                )
            },
            timeout=30
        )

        print("Telegram photo:", response.status_code)

        if not response.ok:
            print("Помилка Telegram photo:", response.text)

        return response.ok

    except Exception as error:

        print("Помилка відправки фото:", error)

        return False


# ============================================================
# ДОПОМІЖНІ ФУНКЦІЇ
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(text)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_text(text):

    text = clean_text(text).lower()

    text = text.replace(
        "’",
        "'"
    )

    text = re.sub(
        r"[^а-яіїєґa-z0-9\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def make_hash(text):

    normalized = normalize_text(text)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def similarity(text1, text2):

    a = normalize_text(text1)
    b = normalize_text(text2)

    if not a or not b:
        return 0

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


# ============================================================
# ОЧИЩЕННЯ ЗАГОЛОВКА
# ============================================================

def clean_news_title(title):

    title = html.unescape(title).strip()

    suffixes = [

        " - Суспільне | Новини",
        " — Суспільне | Новини",
        " - Суспільне Чернігів",
        " — Суспільне Чернігів",
        " - Суспільне",
        " — Суспільне",
        " - ЧЕline",
        " — ЧЕline",
        " - Час Чернігівський",
        " — Час Чернігівський"
    ]

    for suffix in suffixes:

        if title.endswith(suffix):

            title = title[:-len(suffix)].strip()

            break

    return title


# ============================================================
# ЗБЕРЕЖЕНІ НОВИНИ
# ============================================================

def load_seen_news():

    if not os.path.exists(NEWS_SEEN_FILE):
        return set()

    try:

        with open(
            NEWS_SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return set(
                line.strip()
                for line in file
                if line.strip()
            )

    except Exception:

        return set()


def save_seen_news(seen):

    with open(
        NEWS_SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        for item in sorted(seen):

            file.write(
                item + "\n"
            )


# ============================================================
# РОЗШИФРУВАННЯ GOOGLE NEWS URL
# ============================================================

def resolve_news_link(link):

    if not link:
        return link

    if "news.google.com" not in link:
        return link

    if gnewsdecoder is None:

        print(
            "⚠️ googlenewsdecoder не встановлений"
        )

        return link

    try:

        print("Розшифровую Google News URL...")

        result = gnewsdecoder(
            link,
            interval=1
        )

        if result and result.get("status"):

            decoded_url = result.get(
                "decoded_url",
                ""
            )

            if decoded_url:

                print(
                    "Оригінальна стаття:",
                    decoded_url
                )

                return decoded_url

        print(
            "⚠️ Не вдалося розшифрувати Google News URL"
        )

    except Exception as error:

        print(
            "Помилка розшифрування Google News:",
            error
        )

    return link


# ============================================================
# ОТРИМАННЯ ДАНИХ СТАТТІ
# ============================================================

def get_article_data(link):

    try:

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0 Safari/537.36"
            )
        }

        response = requests.get(
            link,
            headers=headers,
            timeout=20,
            allow_redirects=True
        )

        print(
            "Сторінка статті:",
            response.status_code,
            response.url
        )

        if response.status_code != 200:
            return "", ""

        text = response.text

        description = ""
        image = ""
        article_body = ""

        # ----------------------------------------------------
        # META DESCRIPTION
        # ----------------------------------------------------

        patterns = [

            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',

            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',

            r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:description["\']',

            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']'
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.I | re.S
            )

            if match:

                description = html.unescape(
                    match.group(1)
                ).strip()

                if description:
                    break

        # ----------------------------------------------------
        # OG IMAGE
        # ----------------------------------------------------

        image_patterns = [

            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']',

            r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:image["\']',

            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\'](.*?)["\']',

            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']twitter:image["\']'
        ]

        for pattern in image_patterns:

            match = re.search(
                pattern,
                text,
                re.I | re.S
            )

            if match:

                image = html.unescape(
                    match.group(1)
                ).strip()

                if image:
                    break

        # ----------------------------------------------------
        # JSON-LD
        # ----------------------------------------------------

        json_matches = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            text,
            re.I | re.S
        )

        for raw_json in json_matches:

            try:

                data = json.loads(
                    raw_json.strip()
                )

                objects = []

                if isinstance(data, dict):

                    objects.append(data)

                    if isinstance(
                        data.get("@graph"),
                        list
                    ):

                        objects.extend(
                            data["@graph"]
                        )

                elif isinstance(data, list):

                    objects.extend(data)

                for obj in objects:

                    if not isinstance(obj, dict):
                        continue

                    if not article_body:

                        body = obj.get(
                            "articleBody",
                            ""
                        )

                        if body:

                            article_body = clean_text(
                                body
                            )

                    if not image:

                        json_image = obj.get(
                            "image",
                            ""
                        )

                        if isinstance(
                            json_image,
                            str
                        ):

                            image = json_image

                        elif isinstance(
                            json_image,
                            dict
                        ):

                            image = json_image.get(
                                "url",
                                ""
                            )

                        elif isinstance(
                            json_image,
                            list
                        ) and json_image:

                            first_image = json_image[0]

                            if isinstance(
                                first_image,
                                str
                            ):

                                image = first_image

                            elif isinstance(
                                first_image,
                                dict
                            ):

                                image = first_image.get(
                                    "url",
                                    ""
                                )

            except Exception:

                continue

        # ----------------------------------------------------
        # ВИДАЛЯЄМО GOOGLE NEWS СЛУЖБОВИЙ ТЕКСТ
        # ----------------------------------------------------

        bad_texts = [

            "Comprehensive up-to-date news coverage",

            "aggregated from sources all over the world by Google News",

            "Google News"
        ]

        for bad_text in bad_texts:

            if bad_text.lower() in description.lower():

                description = ""

                break

        for bad_text in bad_texts:

            if bad_text.lower() in article_body.lower():

                article_body = ""

                break

        # ----------------------------------------------------
        # ВИБИРАЄМО НАЙКРАЩИЙ ТЕКСТ
        # ----------------------------------------------------

        if article_body and len(article_body) >= 40:

            description = article_body

        description = clean_text(
            description
        )

        # Прибираємо службові фрази
        description = re.sub(
            r"Читайте також.*",
            "",
            description,
            flags=re.IGNORECASE
        ).strip()

        # Прибираємо зайві посилання з тексту
        description = re.sub(
            r"https?://\S+",
            "",
            description
        )

        description = re.sub(
            r"\s+",
            " ",
            description
        ).strip()

        print(
            "Текст статті отримано:",
            len(description),
            "символів"
        )

        if image:

            print(
                "Зображення статті знайдено"
            )

        else:

            print(
                "Зображення статті не знайдено"
            )

        return description, image

    except Exception as error:

        print(
            "Помилка отримання статті:",
            error
        )

        return "", ""


# ============================================================
# GOOGLE NEWS
# ============================================================

def get_google_news(source):

    news = []

    query = source["query"]
    category = source["category"]
    priority = source["priority"]

    url = (
        "https://news.google.com/rss/search?"
        f"q={requests.utils.quote(query)}"
        "&hl=uk&gl=UA&ceid=UA:uk"
    )

    try:

        response = requests.get(
            url,
            timeout=20
        )

        print(
            f"Google News [{category}]:",
            response.status_code
        )

        if not response.ok:
            return news

        root = ET.fromstring(
            response.text
        )

        for item in root.findall(
            ".//item"
        ):

            title = item.findtext(
                "title",
                ""
            )

            link = item.findtext(
                "link",
                ""
            )

            pub_date = item.findtext(
                "pubDate",
                ""
            )

            description = item.findtext(
                "description",
                ""
            )

            if not title or not link:
                continue

            news.append(
                {
                    "title": title,
                    "link": link,
                    "date": pub_date,
                    "description": description,
                    "category": category,
                    "priority": priority
                }
            )

    except Exception as error:

        print(
            "Помилка Google News:",
            error
        )

    return news


# ============================================================
# ОТРИМАННЯ ВСІХ НОВИН
# ============================================================

def get_all_news():

    all_news = []

    for source in NEWS_SOURCES:

        source_news = get_google_news(
            source
        )

        all_news.extend(
            source_news
        )

    return all_news


# ============================================================
# ПЕРЕВІРКА ЧАСУ
# ============================================================

def is_recent(date_string):

    if not date_string:
        return True

    try:

        pub_time = datetime.strptime(
            date_string,
            "%a, %d %b %Y %H:%M:%S %Z"
        ).replace(
            tzinfo=timezone.utc
        )

        now = datetime.now(
            timezone.utc
        )

        age = now - pub_time

        if age < timedelta(
            seconds=0
        ):
            return False

        if age > timedelta(
            hours=MAX_NEWS_AGE_HOURS
        ):
            return False

        return True

    except Exception:

        return True


# ============================================================
# ФІЛЬТР НОВИН
# ============================================================

def allowed_news(item):

    title = normalize_text(
        item["title"]
    )

    category = item["category"]

    sports_words = [

        "футбол",
        "спорт",
        "матч",
        "чемпіонат",
        "баскетбол",
        "теніс",
        "хокей"
    ]

    if any(
        word in title
        for word in sports_words
    ):

        return False

    # --------------------------------------------------------
    # КОЗЕЛЕЦЬ
    # --------------------------------------------------------

    if category == "📍 КОЗЕЛЕЦЬ":

        if (
            "козелець" not in title
            and
            "козелецька громада" not in title
        ):

            return False

    # --------------------------------------------------------
    # ЧЕРНІГІВ
    # --------------------------------------------------------

    if category == "🏙️ ЧЕРНІГІВ":

        oblast_words = [

            "чернігівщина",
            "чернігівській області",
            "чернігівської області",
            "на чернігівщині",
            "по чернігівщині",
            "чернігівщини"
        ]

        if any(
            word in title
            for word in oblast_words
        ):

            return False

        if "чернігів" not in title:

            return False

    return True


# ============================================================
# ДЕДУПЛІКАЦІЯ
# ============================================================

def is_duplicate(item, published_items):

    item_title = item["title"]

    item_description = clean_text(
        item.get(
            "description",
            ""
        )
    )

    item_text = (
        item_title
        + " "
        + item_description
    )

    item_hash = make_hash(
        item_title
        + item_description
    )

    for existing in published_items:

        if existing["hash"] == item_hash:
            return True

    for existing in published_items:

        existing_text = (
            existing["title"]
            + " "
            + existing["description"]
        )

        title_similarity = similarity(
            item_title,
            existing["title"]
        )

        text_similarity = similarity(
            item_text,
            existing_text
        )

        if title_similarity >= 0.82:
            return True

        if (
            title_similarity >= 0.65
            and
            text_similarity >= 0.70
        ):

            return True

    return False


# ============================================================
# ПУБЛІКАЦІЯ НОВИН
# ============================================================

def publish_news():

    seen = load_seen_news()

    raw_news = get_all_news()

    prepared = []

    for item in raw_news:

        if not is_recent(
            item["date"]
        ):
            continue

        if not allowed_news(
            item
        ):
            continue

        if item["link"] in seen:
            continue

        prepared.append(
            item
        )

    prepared.sort(
        key=lambda item: (
            item["priority"],
            item["date"]
        ),
        reverse=False
    )

    published_items = []

    published = 0

    for item in prepared:

        print()
        print(
            "Перевірка:",
            item["title"],
            "| пріоритет:",
            item["priority"]
        )

        # ----------------------------------------------------
        # ОТРИМУЄМО СПРАВЖНЄ ПОСИЛАННЯ
        # ----------------------------------------------------

        real_link = resolve_news_link(
            item["link"]
        )

        # ----------------------------------------------------
        # ОТРИМУЄМО ТЕКСТ І ФОТО
        # ----------------------------------------------------

        article_text, image_url = (
            get_article_data(
                real_link
            )
        )

        # ----------------------------------------------------
        # ЯКЩО СТОРІНКА НЕ ДАЛА ТЕКСТ —
        # RSS ОПИС, АЛЕ БЕЗ GOOGLE NEWS ТЕКСТУ
        # ----------------------------------------------------

        if not article_text:

            article_text = clean_text(
                item.get(
                    "description",
                    ""
                )
            )

        bad_google_text = [

            "Comprehensive up-to-date news coverage",

            "aggregated from sources all over the world",

            "Google News"
        ]

        for bad_text in bad_google_text:

            if bad_text.lower() in article_text.lower():

                article_text = ""

                break

        # ----------------------------------------------------
        # ОЧИЩЕННЯ ЗАГОЛОВКА
        # ----------------------------------------------------

        clean_title = clean_news_title(
            item["title"]
        )

        # ----------------------------------------------------
        # ПОСТІЙНА ПЕРЕВІРКА ДУБЛІКАТІВ
        # ----------------------------------------------------

        title_key = (
            "TITLE:"
            + make_hash(clean_title)
        )

        if title_key in seen:

            print(
                "⏭️ Вже публікувалася:",
                clean_title
            )

            seen.add(
                item["link"]
            )

            continue

        # ----------------------------------------------------
        # ДЕДУПЛІКАЦІЯ В МЕЖАХ ПОТОЧНОГО ЗАПУСКУ
        # ----------------------------------------------------

        temp_item = {

            "title":
                clean_title,

            "description":
                article_text,

            "hash":
                make_hash(
                    clean_title
                    + article_text
                )
        }

        if is_duplicate(
            temp_item,
            published_items
        ):

            print(
                "⏭️ ДУБЛІКАТ:",
                clean_title
            )

            seen.add(
                item["link"]
            )

            continue

        # ----------------------------------------------------
        # ЯКЩО ТЕКСТУ НЕМАЄ
        # ----------------------------------------------------

        if len(article_text) < 20:

            article_text = (
                "Подробиці новини "
                "уточнюються."
            )

        article_text = article_text[:750]

        # ----------------------------------------------------
        # ФОРМУВАННЯ ПОВІДОМЛЕННЯ
        # ----------------------------------------------------

        message = (

            f"{item['category']}\n\n"

            f"📰 {clean_title}\n\n"

            f"{article_text}"
        )

        # ----------------------------------------------------
        # ПУБЛІКАЦІЯ
        # ----------------------------------------------------

        success = False

        if image_url:

            success = send_telegram_photo(
                image_url,
                message
            )

        if not success:

            success = send_telegram(
                message
            )

        # ----------------------------------------------------
        # ЗБЕРІГАЄМО ТІЛЬКИ УСПІШНУ ПУБЛІКАЦІЮ
        # ----------------------------------------------------

        if success:

            seen.add(
                item["link"]
            )

            seen.add(
                title_key
            )

            if real_link:
                seen.add(
                    "URL:"
                    + real_link
                )

            published_items.append(
                temp_item
            )

            published += 1

            print(
                "✅ Опубліковано:",
                clean_title
            )

        else:

            print(
                "❌ Не вдалося опублікувати:",
                clean_title
            )

    save_seen_news(
        seen
    )

    print(
        "Нових новин опубліковано:",
        published
    )


# ============================================================
# ПОГОДА
# ============================================================

WEATHER_CODES = {

    0: "☀️ Ясно",
    1: "🌤 Переважно ясно",
    2: "⛅ Мінлива хмарність",
    3: "☁️ Хмарно",

    45: "🌫 Туман",
    48: "🌫 Туман",

    51: "🌦 Легка мряка",
    53: "🌦 Мряка",
    55: "🌧 Сильна мряка",

    56: "🌧 Крижана мряка",
    57: "🌧 Крижана мряка",

    61: "🌧 Невеликий дощ",
    63: "🌧 Дощ",
    65: "🌧 Сильний дощ",

    66: "🌧 Крижаний дощ",
    67: "🌧 Сильний крижаний дощ",

    71: "🌨 Невеликий сніг",
    73: "🌨 Сніг",
    75: "❄️ Сильний сніг",

    77: "❄️ Снігові зерна",

    80: "🌦 Невелика злива",
    81: "🌧 Злива",
    82: "🌧 Сильна злива",

    85: "🌨 Снігова злива",
    86: "❄️ Сильна снігова злива",

    95: "⛈ Гроза",
    96: "⛈ Гроза з градом",
    99: "⛈ Сильна гроза з градом"
}


def get_weather_for_location(
    name,
    latitude,
    longitude,
    date_string
):

    url = "https://api.open-meteo.com/v1/forecast"

    params = {

        "latitude":
            latitude,

        "longitude":
            longitude,

        "daily":
            ",".join([
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "precipitation_sum",
                "wind_speed_10m_max",
                "sunrise",
                "sunset"
            ]),

        "timezone":
            "Europe/Kyiv",

        "start_date":
            date_string,

        "end_date":
            date_string
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        print(
            f"Погода {name}:",
            response.status_code
        )

        if not response.ok:

            print(
                "Помилка Open-Meteo:",
                response.text
            )

            return None

        data = response.json()

        daily = data.get(
            "daily",
            {}
        )

        times = daily.get(
            "time",
            []
        )

        if not times:
            return None

        weather_code = daily.get(
            "weather_code",
            [None]
        )[0]

        temp_max = daily.get(
            "temperature_2m_max",
            [None]
        )[0]

        temp_min = daily.get(
            "temperature_2m_min",
            [None]
        )[0]

        precipitation_probability = daily.get(
            "precipitation_probability_max",
            [None]
        )[0]

        precipitation = daily.get(
            "precipitation_sum",
            [None]
        )[0]

        wind_max = daily.get(
            "wind_speed_10m_max",
            [None]
        )[0]

        sunrise = daily.get(
            "sunrise",
            [None]
        )[0]

        sunset = daily.get(
            "sunset",
            [None]
        )[0]

        return {

            "name":
                name,

            "weather":
                WEATHER_CODES.get(
                    weather_code,
                    "🌤 Змішані погодні умови"
                ),

            "temp_min":
                temp_min,

            "temp_max":
                temp_max,

            "precipitation_probability":
                precipitation_probability,

            "precipitation":
                precipitation,

            "wind_max":
                wind_max,

            "sunrise":
                sunrise,

            "sunset":
                sunset
        }

    except Exception as error:

        print(
            f"Помилка погоди {name}:",
            error
        )

        return None


def format_weather_block(weather):

    if not weather:
        return "⚠️ Дані погоди тимчасово недоступні."

    lines = [

        f"📍 {weather['name']}",

        f"{weather['weather']}",

        (
            f"🌡 Температура: "
            f"{weather['temp_min']:+.0f}°C ... "
            f"{weather['temp_max']:+.0f}°C"
        )
    ]

    if weather["precipitation_probability"] is not None:

        lines.append(
            f"🌧 Ймовірність опадів: "
            f"{weather['precipitation_probability']}%"
        )

    if weather["precipitation"] is not None:

        lines.append(
            f"💧 Опади: "
            f"{weather['precipitation']:.1f} мм"
        )

    if weather["wind_max"] is not None:

        lines.append(
            f"💨 Вітер: до "
            f"{weather['wind_max']:.0f} км/год"
        )

    if weather["sunrise"]:

        sunrise_time = (
            weather["sunrise"]
            .split("T")[-1]
        )

        lines.append(
            f"🌅 Схід сонця: {sunrise_time}"
        )

    if weather["sunset"]:

        sunset_time = (
            weather["sunset"]
            .split("T")[-1]
        )

        lines.append(
            f"🌇 Захід сонця: {sunset_time}"
        )

    return "\n".join(lines)


def load_weather_state():

    if not os.path.exists(
        WEATHER_STATE_FILE
    ):

        return {}

    try:

        with open(
            WEATHER_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            state = {}

            for line in file:

                if "=" in line:

                    key, value = line.strip().split(
                        "=",
                        1
                    )

                    state[key] = value

            return state

    except Exception:

        return {}


def save_weather_state(state):

    with open(
        WEATHER_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        for key, value in state.items():

            file.write(
                f"{key}={value}\n"
            )


def check_weather():

    now = datetime.now(
        KYIV_TZ
    )

    state = load_weather_state()

    today = now.date()

    # --------------------------------------------------------
    # РАНОК — 08:00–08:59
    # ПРОГНОЗ НА СЬОГОДНІ
    # --------------------------------------------------------

    if now.hour == 8:

        state_key = (
            "morning_"
            + today.isoformat()
        )

        if state.get("morning") != today.isoformat():

            print(
                "=== Ранковий прогноз погоди ==="
            )

            kozelets = get_weather_for_location(
                "Козелець",
                KOZELETS_LAT,
                KOZELETS_LON,
                today.isoformat()
            )

            chernihiv = get_weather_for_location(
                "Чернігів",
                CHERNIHIV_LAT,
                CHERNIHIV_LON,
                today.isoformat()
            )

            message = (

                "🌤 ПОГОДА НА СЬОГОДНІ\n\n"

                f"📅 {today.strftime('%d.%m.%Y')}\n\n"

                f"{format_weather_block(kozelets)}\n\n"

                "━━━━━━━━━━━━━━\n\n"

                f"{format_weather_block(chernihiv)}"
            )

            if send_telegram(message):

                state["morning"] = today.isoformat()

                save_weather_state(
                    state
                )

                print(
                    "✅ Ранковий прогноз відправлено"
                )

    # --------------------------------------------------------
    # ВЕЧІР — 20:00–20:59
    # ПРОГНОЗ НА ЗАВТРА
    # --------------------------------------------------------

    if now.hour == 20:

        tomorrow = today + timedelta(
            days=1
        )

        if state.get("evening") != today.isoformat():

            print(
                "=== Вечірній прогноз погоди ==="
            )

            kozelets = get_weather_for_location(
                "Козелець",
                KOZELETS_LAT,
                KOZELETS_LON,
                tomorrow.isoformat()
            )

            chernihiv = get_weather_for_location(
                "Чернігів",
                CHERNIHIV_LAT,
                CHERNIHIV_LON,
                tomorrow.isoformat()
            )

            message = (

                "🌤 ПОГОДА НА ЗАВТРА\n\n"

                f"📅 {tomorrow.strftime('%d.%m.%Y')}\n\n"

                f"{format_weather_block(kozelets)}\n\n"

                "━━━━━━━━━━━━━━\n\n"

                f"{format_weather_block(chernihiv)}"
            )

            if send_telegram(message):

                state["evening"] = today.isoformat()

                save_weather_state(
                    state
                )

                print(
                    "✅ Вечірній прогноз відправлено"
                )


# ============================================================
# NEPTUN
# ============================================================

def load_alert_states():

    states = {}

    if not os.path.exists(
        ALERT_STATE_FILE
    ):

        return states

    with open(
        ALERT_STATE_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            if "=" in line:

                name, state = (
                    line.strip().split(
                        "=",
                        1
                    )
                )

                states[name] = (
                    state == "true"
                )

    return states


def save_alert_states(states):

    with open(
        ALERT_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        for name, active in states.items():

            file.write(
                f"{name}="
                f"{'true' if active else 'false'}\n"
            )


def check_neptun():

    old_states = load_alert_states()

    try:

        url = (
            "https://neptun.in.ua/"
            "api/v1/alerts"
        )

        response = requests.get(
            url,
            timeout=20
        )

        print(
            "NEPTUN API:",
            response.status_code
        )

        if not response.ok:

            print(
                "Помилка NEPTUN:",
                response.text
            )

            return

        data = response.json()

        active_regions = set()
        active_districts = set()

        for item in data.get(
            "oblasts",
            []
        ):

            name = item.get(
                "name",
                ""
            )

            if name:
                active_regions.add(name)

        for item in data.get(
            "raions",
            []
        ):

            name = item.get(
                "name",
                ""
            )

            if name:
                active_districts.add(name)

        checks = {

            "Чернігівська область":
                "Чернігівська область"
                in active_regions,

            "Чернігівський район":
                "Чернігівський район"
                in active_districts
        }

        new_states = old_states.copy()

        for name, active in checks.items():

            old_active = old_states.get(
                name,
                False
            )

            print(
                name,
                "активна:",
                active
            )

            # НОВА ТРИВОГА

            if (
                active
                and
                not old_active
            ):

                success = send_telegram(

                    f"🔴 ПОВІТРЯНА ТРИВОГА\n\n"

                    f"📍 {name}\n\n"

                    f"⚠️ Стежте за офіційними "
                    f"повідомленнями."
                )

                if success:

                    new_states[name] = True

                else:

                    print(
                        "⚠️ Тривогу не вдалося "
                        "відправити."
                    )

            # ВІДБІЙ

            elif (
                not active
                and
                old_active
            ):

                success = send_telegram(

                    f"🟢 ВІДБІЙ "
                    f"ПОВІТРЯНОЇ ТРИВОГИ\n\n"

                    f"📍 {name}"
                )

                if success:

                    new_states[name] = False

                else:

                    print(
                        "⚠️ Відбій не вдалося "
                        "відправити."
                    )

            else:

                new_states[name] = active

        save_alert_states(
            new_states
        )

    except Exception as error:

        print(
            "Помилка перевірки NEPTUN:",
            error
        )


# ============================================================
# MAPA.UA
# ============================================================

def load_mapa_state():

    if not os.path.exists(
        MAPA_STATE_FILE
    ):

        return False

    try:

        with open(
            MAPA_STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return (
                file.read().strip()
                == "true"
            )

    except Exception:

        return False


def save_mapa_state(active):

    with open(
        MAPA_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "true"
            if active
            else "false"
        )


def check_mapa():

    old_active = load_mapa_state()

    try:

        url = (
            "https://mapa.ua/"
            "api/v1/nearby"
        )

        params = {

            "lat":
                KOZELETS_LAT,

            "lon":
                KOZELETS_LON,

            "radius_km":
                MAPA_RADIUS_KM
        }

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        print(
            "MAPA.UA API:",
            response.status_code
        )

        if not response.ok:

            print(
                "Помилка MAPA.UA:",
                response.text
            )

            return

        data = response.json()

        threats = data.get(
            "threats",
            []
        )

        active = len(threats) > 0

        print(
            "MAPA.UA: активних загроз:",
            len(threats)
        )

        # НОВА ЗАГРОЗА

        if (
            active
            and
            not old_active
        ):

            success = send_telegram(

                "⚠️ ДОДАТКОВА ІНФОРМАЦІЯ\n\n"

                "🗺️ MAPA.UA повідомляє "
                "про активні повітряні загрози "
                "поблизу Козельця.\n\n"

                "⚠️ Дані MAPA.UA є приблизними "
                "та не замінюють офіційні "
                "повідомлення про повітряну тривогу."
            )

            if success:

                save_mapa_state(True)

        # ЗАГРОЗИ ЗНИКЛИ

        elif (
            not active
            and
            old_active
        ):

            success = send_telegram(

                "ℹ️ MAPA.UA\n\n"

                "Активних загроз поблизу "
                "Козельця більше не виявлено.\n\n"

                "⚠️ Це додаткове інформаційне "
                "повідомлення і не є офіційним "
                "відбоєм повітряної тривоги."
            )

            if success:

                save_mapa_state(False)

        else:

            save_mapa_state(active)

    except Exception as error:

        print(
            "Помилка перевірки MAPA.UA:",
            error
        )


# ============================================================
# ЗАПУСК
# ============================================================

def main():

    print(
        "=== Перевірка Козелець Alarm ==="
    )

    publish_news()

    check_weather()

    check_neptun()

    check_mapa()

    print(
        "=== Перевірку завершено ==="
    )


if __name__ == "__main__":

    main()
