import os
import re
import html
import time
import hashlib
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta
from urllib.parse import quote, urljoin
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import new_decoderv1
except Exception:
    new_decoderv1 = None


# =========================================================
# НАЛАШТУВАННЯ
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL = os.getenv("CHANNEL", "").strip()

# Ключ НЕ зберігаємо у коді.
# Додай його у GitHub Secrets:
# UKRAINE_ALARM_API_KEY
UKRAINE_ALARM_API_KEY = os.getenv(
    "UKRAINE_ALARM_API_KEY",
    ""
).strip()

TIMEZONE = ZoneInfo("Europe/Kyiv")

# Козелець
KOZELETS_LAT = 50.913
KOZELETS_LON = 31.115

# API / сайти
UKRAINE_ALARM_URL = (
    "https://api.ukrainealarm.com/api/v3/alerts"
)

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
)

CHERNIHIV_OBLENERGO_URL = (
    "https://chernihivoblenergo.com.ua/blackouts"
)

UKR_HYDROMET_RAD_URL = (
    "https://www.meteo.gov.ua/ua/Radiolohichni-poperedzhennya"
)

NKRZU_RAD_URL = (
    "https://nkrzu.gov.ua/res/rad"
)

WATER_URL = (
    "https://neptun.in.ua/"
)

# Файли стану
NEWS_STATE_FILE = "news_seen.txt"
ALERT_STATE_FILE = "alert_state.txt"
RAD_STATE_FILE = "rad_state.txt"
POWER_STATE_FILE = "power_state.txt"
PINNED_MSG_ID_FILE = "pinned_msg_id.txt"
HISTORY_INDEX_FILE = "history_index.txt"
HISTORY_LAST_TIME_FILE = "history_last_time.txt"
LAST_WEATHER_FILE = "weather_state.txt"

# Скільки часу новина вважається свіжою
NEWS_MAX_AGE_HOURS = 8

# Максимальна кількість новин за один запуск
MAX_NEWS_PER_RUN = 8

# Історичний пост кожні 12 годин
HISTORY_INTERVAL_HOURS = 12

# Telegram limits
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_CAPTION_LIMIT = 1024


# =========================================================
# HTTP SESSION
# =========================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.7",
    }
)


# =========================================================
# ІСТОРИЧНІ ФАКТИ
# =========================================================

KOZELETS_HISTORY_FACTS = [
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Собор Різдва Богородиці\n\n"
        "Головна архітектурна перлина Козельця, збудована "
        "у XVIII столітті. Собор відомий своїм величним "
        "українським бароковим стилем та унікальним "
        "іконостасом."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Козелець\n\n"
        "Козелець має багатовікову історію та відігравав "
        "важливу роль у житті Лівобережної України. "
        "Місто відоме численними пам'ятками XVIII століття."
    ),
    (
        "👥 ВИДАТНІ ЛЮДИ: Родина Розумовських\n\n"
        "Козелець тісно пов'язаний із родиною Розумовських. "
        "Їхній вплив помітний у розвитку архітектури та "
        "культурного життя краю."
    ),
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Будинок полкової канцелярії\n\n"
        "Одна з найвідоміших історичних споруд Козельця. "
        "Пам'ятка пов'язана з адміністративною історією "
        "міста XVIII століття."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Остер\n\n"
        "Остер — одне з найдавніших міст Чернігівщини. "
        "Місто має історію, яка сягає часів Київської Русі."
    ),
    (
        "👥 ВИДАТНІ ЛЮДИ: Павло Чубинський\n\n"
        "Павло Чубинський — український етнограф, фольклорист "
        "та автор тексту Державного Гімну України. "
        "Його наукова діяльність була тісно пов'язана "
        "з дослідженням українського народу."
    ),
    (
        "🏛️ ВИДАТНІ БУДІВЛІ: Миколаївська церква\n\n"
        "Історична сакральна споруда Козельця, яка є частиною "
        "архітектурної спадщини міста."
    ),
    (
        "📜 ІСТОРИЧНІ ФАКТИ: Магдебурзьке право\n\n"
        "Надання містам Магдебурзького права сприяло розвитку "
        "місцевого самоврядування, торгівлі та міського життя."
    ),
    (
        "🌊 КРАЄЗНАВСТВО: Десна\n\n"
        "Десна є однією з найбільших річок Чернігівщини "
        "та відіграє важливу роль у природі, господарстві "
        "і культурі регіону."
    ),
    (
        "🌳 КРАЄЗНАВСТВО: Чернігівщина\n\n"
        "Край поєднує давню історію, річкові долини, ліси, "
        "старовинні міста та численні архітектурні пам'ятки."
    ),
]


# =========================================================
# ДЖЕРЕЛА НОВИН
# =========================================================

NEWS_SOURCES = [
    # Козелець
    {
        "query": "site:cheline.com.ua Козелець",
        "category": "📍 КОЗЕЛЕЦЬ",
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

    # Остер
    {
        "query": "site:cheline.com.ua Остер",
        "category": "📍 ОСТЕР",
        "priority": 1,
    },
    {
        "query": "site:suspilne.media/chernihiv Остер",
        "category": "📍 ОСТЕР",
        "priority": 2,
    },
    {
        "query": "\"Остер\" новини міста",
        "category": "📍 ОСТЕР",
        "priority": 3,
    },

    # Бобровиця
    {
        "query": "site:cheline.com.ua Бобровиця",
        "category": "📍 БОБРОВИЦЯ",
        "priority": 1,
    },
    {
        "query": "site:suspilne.media/chernihiv Бобровиця",
        "category": "📍 БОБРОВИЦЯ",
        "priority": 2,
    },
    {
        "query": "\"Бобровиця\" новини громади",
        "category": "📍 БОБРОВИЦЯ",
        "priority": 3,
    },

    # Козелеччина
    {
        "query": "\"Козелеччина\" новини",
        "category": "📍 КОЗЕЛЕЧЧИНА",
        "priority": 1,
    },
    {
        "query": "\"Козелецький район\" новини",
        "category": "📍 КОЗЕЛЕЧЧИНА",
        "priority": 2,
    },

    # Комунальні теми
    {
        "query": "\"Козелець\" світло вода",
        "category": "🚰 КОМУНАЛКА",
        "priority": 1,
    },
    {
        "query": "\"Козелець\" електроенергія",
        "category": "⚡ ЕНЕРГЕТИКА",
        "priority": 1,
    },
    {
        "query": "\"Козелець\" дороги",
        "category": "🚧 ІНФРАСТРУКТУРА",
        "priority": 2,
    },

    # ДСНС
    {
        "query": "site:dsns.gov.ua Чернігівська область Козелець",
        "category": "🚒 ДСНС",
        "priority": 1,
    },
    {
        "query": "site:dsns.gov.ua Чернігівська область Остер",
        "category": "🚒 ДСНС",
        "priority": 1,
    },
    {
        "query": "site:dsns.gov.ua Чернігівська область Бобровиця",
        "category": "🚒 ДСНС",
        "priority": 1,
    },
    {
        "query": "\"ДСНС\" \"Козелець\"",
        "category": "🚒 ДСНС",
        "priority": 2,
    },

    # Поліція
    {
        "query": "site:npu.gov.ua Чернігівська область Козелець",
        "category": "👮 ПОЛІЦІЯ",
        "priority": 1,
    },
    {
        "query": "site:npu.gov.ua Чернігівська область Остер",
        "category": "👮 ПОЛІЦІЯ",
        "priority": 1,
    },
    {
        "query": "site:npu.gov.ua Чернігівська область Бобровиця",
        "category": "👮 ПОЛІЦІЯ",
        "priority": 1,
    },
]


# =========================================================
# ЗАГАЛЬНІ HTTP ФУНКЦІЇ
# =========================================================

def safe_get(url, timeout=8, headers=None):
    try:
        response = SESSION.get(
            url,
            timeout=timeout,
            headers=headers,
            allow_redirects=True,
        )

        return response

    except requests.RequestException as exc:
        print(f"HTTP error: {url} -> {exc}")

    except Exception as exc:
        print(f"HTTP unknown error: {url} -> {exc}")

    return None


# =========================================================
# TELEGRAM
# =========================================================

def telegram_url(method):
    return (
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    )


def telegram_request(method, data=None, timeout=10):
    if not BOT_TOKEN:
        print("BOT_TOKEN не заданий.")
        return None

    try:
        response = SESSION.post(
            telegram_url(method),
            data=data or {},
            timeout=timeout,
        )

        if response.ok:
            return response.json()

        print(
            f"Telegram {method}: "
            f"{response.status_code} {response.text[:500]}"
        )

    except Exception as exc:
        print(f"Telegram {method}: {exc}")

    return None


def limit_text(text, limit):
    if not text:
        return ""

    text = str(text)

    if len(text) <= limit:
        return text

    cut = text[:limit - 30]

    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]

    return cut.rstrip() + "\n\n…"


def send_message(text, disable_preview=True):
    if not BOT_TOKEN or not CHANNEL:
        print("BOT_TOKEN або CHANNEL не задані.")
        return None

    text = limit_text(text, TELEGRAM_MESSAGE_LIMIT)

    result = telegram_request(
        "sendMessage",
        {
            "chat_id": CHANNEL,
            "text": text,
            "disable_web_page_preview": disable_preview,
        },
    )

    if result and result.get("ok"):
        return result["result"]["message_id"]

    return None


def send_photo(photo_url, caption):
    if not BOT_TOKEN or not CHANNEL:
        return None

    if not photo_url:
        return None

    caption = limit_text(
        caption,
        TELEGRAM_CAPTION_LIMIT,
    )

    result = telegram_request(
        "sendPhoto",
        {
            "chat_id": CHANNEL,
            "photo": photo_url,
            "caption": caption,
        },
        timeout=15,
    )

    if result and result.get("ok"):
        return result["result"]["message_id"]

    return None


def edit_message(message_id, text, disable_preview=True):
    if not message_id:
        return False

    text = limit_text(
        text,
        TELEGRAM_MESSAGE_LIMIT,
    )

    result = telegram_request(
        "editMessageText",
        {
            "chat_id": CHANNEL,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": disable_preview,
        },
    )

    if result and result.get("ok"):
        return True

    return False


def pin_message(message_id):
    if not message_id:
        return False

    result = telegram_request(
        "pinChatMessage",
        {
            "chat_id": CHANNEL,
            "message_id": message_id,
            "disable_notification": True,
        },
        timeout=8,
    )

    return bool(result and result.get("ok"))


# =========================================================
# ФАЙЛИ СТАНУ
# =========================================================

def read_state(filename):
    try:
        with open(
            filename,
            "r",
            encoding="utf-8",
        ) as file:
            return file.read().strip()

    except FileNotFoundError:
        return ""

    except Exception as exc:
        print(f"Read state {filename}: {exc}")
        return ""


def write_state(filename, value):
    try:
        with open(
            filename,
            "w",
            encoding="utf-8",
        ) as file:
            file.write(str(value))

        return True

    except Exception as exc:
        print(f"Write state {filename}: {exc}")
        return False


# =========================================================
# ТЕКСТ
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(str(text))

    text = re.sub(
        r"<script.*?</script>",
        " ",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<style.*?</style>",
        " ",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"https?://\S+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def clean_title(title):
    title = clean_text(title)

    patterns = [
        r"\s+-\s+Суспільне.*$",
        r"\s+-\s+ЧЕline.*$",
        r"\s+-\s+Вісник Ч.*$",
        r"\s+-\s+Час Чернігівський.*$",
        r"\s+\|\s+Суспільне.*$",
        r"\s+\|\s+ЧЕline.*$",
        r"\s+-\s+Новини Чернігова.*$",
    ]

    for pattern in patterns:
        title = re.sub(
            pattern,
            "",
            title,
            flags=re.IGNORECASE,
        )

    return title.strip()


# =========================================================
# GOOGLE NEWS
# =========================================================

def resolve_news_link(link):
    if not link:
        return ""

    if "news.google.com" not in link:
        return link

    if new_decoderv1 is None:
        return link

    try:
        result = new_decoderv1(
            link,
            interval_time=0.3,
        )

        if isinstance(result, dict):
            if result.get("status") and result.get("url"):
                return result["url"]

        if isinstance(result, str) and result.startswith("http"):
            return result

    except Exception as exc:
        print(f"Google News decoder: {exc}")

    return link


def get_google_news(query):
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}"
        "&hl=uk"
        "&gl=UA"
        "&ceid=UA:uk"
    )

    response = safe_get(url, timeout=10)

    if not response or not response.ok:
        return []

    try:
        root = ET.fromstring(response.content)

    except ET.ParseError as exc:
        print(f"RSS XML error: {exc}")
        return []

    except Exception as exc:
        print(f"RSS parse error: {exc}")
        return []

    news = []

    for item in root.findall(".//item"):
        title = clean_title(
            item.findtext("title", "")
        )

        link = item.findtext(
            "link",
            "",
        ).strip()

        description = clean_text(
            item.findtext(
                "description",
                "",
            )
        )

        pub_date = item.findtext(
            "pubDate",
            "",
        )

        try:
            date = parsedate_to_datetime(
                pub_date
            ).astimezone(TIMEZONE)

        except Exception:
            date = datetime.now(TIMEZONE)

        if not title or not link:
            continue

        news.append(
            {
                "title": title,
                "link": link,
                "description": description,
                "date": date,
            }
        )

    return news


# =========================================================
# СТАТТЯ
# =========================================================

def extract_article_data(url):
    if not url:
        return "", ""

    if "news.google.com" in url:
        return "", ""

    response = safe_get(
        url,
        timeout=8,
        headers={
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
        },
    )

    if not response or not response.ok:
        return "", ""

    page = response.text

    image_url = ""
    description = ""

    # og:image
    image_patterns = [
        r'<meta[^>]+property=["\']og:image["\']'
        r'[^>]+content=["\']([^"\']+)["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\']'
        r'[^>]+property=["\']og:image["\']',
    ]

    for pattern in image_patterns:
        match = re.search(
            pattern,
            page,
            flags=re.I,
        )

        if match:
            image_url = html.unescape(
                match.group(1)
            ).strip()

            break

    # description
    description_patterns = [
        r'<meta[^>]+name=["\']description["\']'
        r'[^>]+content=["\']([^"\']+)["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\']'
        r'[^>]+name=["\']description["\']',
    ]

    for pattern in description_patterns:
        match = re.search(
            pattern,
            page,
            flags=re.I,
        )

        if match:
            description = clean_text(
                html.unescape(match.group(1))
            )

            break

    if image_url:
        image_url = urljoin(
            response.url,
            image_url,
        )

        if image_url.startswith("//"):
            image_url = "https:" + image_url

    if len(description) > 800:
        description = (
            description[:800]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return description, image_url


# =========================================================
# ДУБЛІКАТИ
# =========================================================

def normalize_title(title):
    title = str(title).lower()

    title = re.sub(
        r"[^а-яіїєґa-z0-9 ]",
        " ",
        title,
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip()


def similar_titles(a, b):
    a_words = set(
        normalize_title(a).split()
    )

    b_words = set(
        normalize_title(b).split()
    )

    if not a_words or not b_words:
        return False

    common = len(
        a_words & b_words
    )

    minimum = min(
        len(a_words),
        len(b_words),
    )

    if minimum < 5:
        return False

    return (
        common / minimum >= 0.65
    )


def make_news_id(title, link=""):
    normalized = normalize_title(title)

    # Основний ідентифікатор за заголовком.
    # Це дозволяє відловлювати дублікати
    # між різними Google News запитами.
    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def load_seen_items():
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


def save_seen_items(items):
    # Не даємо файлу безкінечно рости.
    ordered = list(items)[-3000:]

    try:
        with open(
            NEWS_STATE_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            for item in ordered:
                file.write(
                    item + "\n"
                )

    except Exception as exc:
        print(
            f"Save news state: {exc}"
        )


# =========================================================
# ПЕРЕВІРКА НОВИН
# =========================================================

def is_local_news(title):
    lower = title.lower()

    keywords = [
        "козелець",
        "козелеч",
        "остер",
        "бобровиц",
    ]

    return any(
        word in lower
        for word in keywords
    )


def format_news_post(
    category,
    title,
    article_text,
    link,
):
    text = (
        f"{category}\n\n"
        f"📰 {title}\n\n"
        f"{article_text}"
    )

    if link:
        text += (
            "\n\n🔗 Джерело:\n"
            f"{link}"
        )

    return text


def check_news():
    print("📰 Перевіряю новини...")

    seen = load_seen_items()
    prepared = []

    now = datetime.now(
        TIMEZONE
    )

    for source in NEWS_SOURCES:

        items = get_google_news(
            source["query"]
        )

        for item in items:

            title = item["title"]

            if not title:
                continue

            age_seconds = (
                now - item["date"]
            ).total_seconds()

            if age_seconds < -3600:
                # Майбутні дати RSS — не публікуємо.
                continue

            if age_seconds > (
                NEWS_MAX_AGE_HOURS * 3600
            ):
                continue

            if not is_local_news(title):
                continue

            news_id = make_news_id(
                title,
                item["link"],
            )

            if news_id in seen:
                continue

            prepared.append(
                {
                    "id": news_id,
                    "title": title,
                    "link": item["link"],
                    "description": (
                        item["description"]
                    ),
                    "date": item["date"],
                    "category": (
                        source["category"]
                    ),
                    "priority": (
                        source["priority"]
                    ),
                }
            )

    # Спочатку важливість, потім свіжість.
    prepared.sort(
        key=lambda item: (
            item["priority"],
            -item["date"].timestamp(),
        )
    )

    unique = []

    for item in prepared:

        duplicate = any(
            similar_titles(
                item["title"],
                existing["title"],
            )
            for existing in unique
        )

        if not duplicate:
            unique.append(item)

    # Не засипаємо канал новинами за один запуск.
    unique = unique[:MAX_NEWS_PER_RUN]

    published = 0

    for item in unique:

        print(
            f"Новина: {item['title']}"
        )

        url = resolve_news_link(
            item["link"]
        )

        article_text, image_url = (
            extract_article_data(url)
        )

        if not article_text:
            article_text = (
                item["description"]
                or "Подробиці новини уточнюються."
            )

        caption = format_news_post(
            item["category"],
            item["title"],
            article_text,
            url or item["link"],
        )

        message_id = None

        if image_url:
            message_id = send_photo(
                image_url,
                caption,
            )

        if not message_id:
            message_id = send_message(
                caption
            )

        if message_id:
            seen.add(item["id"])
            published += 1

            # Невелика пауза між публікаціями.
            time.sleep(1)

    save_seen_items(seen)

    print(
        f"📰 Опубліковано новин: {published}"
    )


# =========================================================
# UKRAINE ALARM
# =========================================================

def get_alarm_state():
    if not UKRAINE_ALARM_API_KEY:
        print(
            "⚠️ UKRAINE_ALARM_API_KEY "
            "не заданий."
        )
        return None

    headers = {
        "Accept": "application/json",
        "Authorization": (
            UKRAINE_ALARM_API_KEY
        ),
    }

    response = safe_get(
        UKRAINE_ALARM_URL,
        timeout=8,
        headers=headers,
    )

    if not response:
        return None

    if not response.ok:
        print(
            "UkraineAlarm:",
            response.status_code,
            response.text[:500],
        )
        return None

    try:
        data = response.json()

    except Exception as exc:
        print(
            "UkraineAlarm JSON:",
            exc,
        )
        return None

    if not isinstance(data, list):
        return None

    # Чернігівська область
    for region in data:

        if not isinstance(
            region,
            dict,
        ):
            continue

        region_name = str(
            region.get(
                "regionName",
                "",
            )
        ).lower()

        if (
            "чернігів" not in region_name
            and "chernihiv" not in region_name
        ):
            continue

        active_alerts = (
            region.get(
                "activeAlerts"
            )
        )

        return bool(active_alerts)

    return False


def check_alerts():
    current_state = get_alarm_state()

    if current_state is None:
        # Не змінюємо старий стан при помилці API.
        print(
            "⚠️ Стан тривоги не отримано."
        )
        return (
            read_state(
                ALERT_STATE_FILE
            ) == "1"
        )

    old_state = (
        read_state(
            ALERT_STATE_FILE
        ) == "1"
    )

    if (
        current_state
        and not old_state
    ):
        message_id = send_message(
            "🚨 ПОВІТРЯНА ТРИВОГА\n\n"
            "Чернігівська область!\n\n"
            "⚠️ Негайно перейдіть "
            "в укриття та стежте за "
            "офіційними повідомленнями."
        )

        if message_id:
            write_state(
                ALERT_STATE_FILE,
                "1",
            )

            print(
                "🚨 Опубліковано тривогу."
            )

    elif (
        not current_state
        and old_state
    ):
        message_id = send_message(
            "🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
            "Чернігівська область.\n\n"
            "Стежте за офіційними повідомленнями."
        )

        if message_id:
            write_state(
                ALERT_STATE_FILE,
                "0",
            )

            print(
                "🟢 Опубліковано відбій."
            )

    elif current_state:
        # Стан вже був тривожним.
        write_state(
            ALERT_STATE_FILE,
            "1",
        )

    else:
        write_state(
            ALERT_STATE_FILE,
            "0",
        )

    return current_state


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

    56: "🌧️ Крижаний дощ",
    57: "🌧️ Крижаний дощ",

    61: "🌦️ Невеликий дощ",
    63: "🌧️ Дощ",
    65: "🌧️ Сильний дощ",

    66: "🌧️ Крижаний дощ",
    67: "🌧️ Крижаний дощ",

    71: "🌨️ Невеликий сніг",
    73: "🌨️ Сніг",
    75: "❄️ Сильний сніг",
    77: "🌨️ Снігова крупа",

    80: "🌦️ Злива",
    81: "🌧️ Злива",
    82: "⛈️ Сильна злива",

    85: "🌨️ Снігова злива",
    86: "🌨️ Сильна снігова злива",

    95: "⛈️ Гроза",
    96: "⛈️ Гроза з градом",
    99: "⛈️ Сильна гроза з градом",
}


def get_weather():
    url = (
        f"{OPEN_METEO_URL}"
        f"?latitude={KOZELETS_LAT}"
        f"&longitude={KOZELETS_LON}"
        "&current="
        "temperature_2m,"
        "relative_humidity_2m,"
        "apparent_temperature,"
        "precipitation,"
        "weather_code,"
        "wind_speed_10m,"
        "wind_direction_10m"
        "&hourly="
        "temperature_2m,"
        "precipitation_probability,"
        "weather_code"
        "&forecast_days=2"
        "&timezone=Europe%2FKyiv"
    )

    response = safe_get(
        url,
        timeout=8,
    )

    if not response or not response.ok:
        return None

    try:
        data = response.json()

        current = data["current"]

        return {
            "temperature": (
                current.get(
                    "temperature_2m"
                )
            ),
            "feels_like": (
                current.get(
                    "apparent_temperature"
                )
            ),
            "humidity": (
                current.get(
                    "relative_humidity_2m"
                )
            ),
            "precipitation": (
                current.get(
                    "precipitation"
                )
            ),
            "wind_speed": (
                current.get(
                    "wind_speed_10m"
                )
            ),
            "wind_direction": (
                current.get(
                    "wind_direction_10m"
                )
            ),
            "weather_code": (
                current.get(
                    "weather_code"
                )
            ),
        }

    except Exception as exc:
        print(
            "Weather JSON:",
            exc,
        )

    return None


def wind_direction_text(degrees):
    if degrees is None:
        return ""

    directions = [
        "Пн",
        "Пн-Сх",
        "Сх",
        "Пд-Сх",
        "Пд",
        "Пд-Зх",
        "Зх",
        "Пн-Зх",
    ]

    index = int(
        (degrees + 22.5) / 45
    ) % 8

    return directions[index]


def format_weather_short():
    data = get_weather()

    if not data:
        return "Дані недоступні"

    code = data["weather_code"]

    weather = WEATHER_CODES.get(
        code,
        "🌤️ Погода",
    )

    temperature = data["temperature"]
    feels = data["feels_like"]

    if temperature is None:
        return "Дані недоступні"

    result = (
        f"{weather}, "
        f"{temperature:.1f}°C"
    )

    if feels is not None:
        result += (
            f" (відчувається "
            f"{feels:.1f}°C)"
        )

    return result


def format_weather_detailed():
    data = get_weather()

    if not data:
        return (
            "🌤️ Погода: "
            "дані тимчасово недоступні."
        )

    code = data["weather_code"]

    weather = WEATHER_CODES.get(
        code,
        "🌤️ Погода",
    )

    lines = [
        "🌤️ ПОГОДА — КОЗЕЛЕЦЬ",
        "",
        f"{weather}",
    ]

    if data["temperature"] is not None:
        lines.append(
            f"🌡️ Температура: "
            f"{data['temperature']:.1f}°C"
        )

    if data["feels_like"] is not None:
        lines.append(
            f"🤚 Відчувається: "
            f"{data['feels_like']:.1f}°C"
        )

    if data["humidity"] is not None:
        lines.append(
            f"💧 Вологість: "
            f"{data['humidity']}%"
        )

    if data["wind_speed"] is not None:
        direction = wind_direction_text(
            data["wind_direction"]
        )

        wind_text = (
            f"{data['wind_speed']:.1f} км/год"
        )

        if direction:
            wind_text += (
                f", {direction}"
            )

        lines.append(
            f"💨 Вітер: {wind_text}"
        )

    if data["precipitation"] is not None:
        lines.append(
            f"🌧️ Опади: "
            f"{data['precipitation']} мм"
        )

    return "\n".join(lines)


# =========================================================
# РАДІАЦІЯ
# =========================================================

def parse_radiation_status(page_text):
    text = clean_text(page_text).lower()

    if not text:
        return None

    # Сторінка УкрГМЦ може змінювати формулювання.
    if (
        "знаходиться в своїх звичних межах"
        in text
    ):
        return (
            "🟢 В межах звичних значень"
        )

    if (
        "звичних межах" in text
        or "фоновому рівні" in text
    ):
        return (
            "🟢 Радіаційна ситуація "
            "без небезпечних змін"
        )

    if "червон" in text:
        return (
            "🔴 Потрібна увага: "
            "перевірте офіційні повідомлення"
        )

    if "помаранч" in text:
        return (
            "🟠 Потрібно стежити "
            "за офіційними повідомленнями"
        )

    if "жовт" in text:
        return (
            "🟡 Є попередження "
            "на радіологічній карті"
        )

    return None


def get_radiation_status():
    response = safe_get(
        UKR_HYDROMET_RAD_URL,
        timeout=10,
    )

    if response and response.ok:
        status = parse_radiation_status(
            response.text
        )

        if status:
            return status

    return (
        "ℹ️ Дані дивіться на "
        "офіційній радіологічній карті"
    )


def check_radiation():
    value = get_radiation_status()

    previous = read_state(
        RAD_STATE_FILE
    )

    if not previous:
        write_state(
            RAD_STATE_FILE,
            value,
        )

    return value


# =========================================================
# ЕЛЕКТРОЕНЕРГІЯ
# =========================================================

def get_power_status():
    response = safe_get(
        CHERNIHIV_OBLENERGO_URL,
        timeout=10,
    )

    if not response or not response.ok:
        return {
            "status": "unknown",
            "text": (
                "⚡ Дані про відключення "
                "тимчасово недоступні."
            ),
        }

    page = clean_text(
        response.text
    )

    lower = page.lower()

    # Важливо:
    # ми не визначаємо стан конкретної адреси.
    # Сайт Чернігівобленерго використовує
    # ЕІС-код або особовий рахунок.
    emergency_words = [
        "аварійн",
        "перерв",
        "відключенн",
        "обмеженн",
    ]

    has_notice = any(
        word in lower
        for word in emergency_words
    )

    if has_notice:
        status = (
            "⚠️ Є актуальна інформація "
            "про відключення/перерви"
        )
    else:
        status = (
            "🟢 На сторінці немає "
            "попередження про загальні "
            "відключення"
        )

    return {
        "status": "notice" if has_notice else "ok",
        "text": status,
    }


def check_power():
    data = get_power_status()

    text = data["text"]

    previous = read_state(
        POWER_STATE_FILE
    )

    if previous != text:
        write_state(
            POWER_STATE_FILE,
            text,
        )

    return text


# =========================================================
# ІСТОРИЧНІ ПОСТИ
# =========================================================

def check_and_send_history_post():
    now = datetime.now(
        TIMEZONE
    )

    current_timestamp = (
        now.timestamp()
    )

    last_time_str = read_state(
        HISTORY_LAST_TIME_FILE
    )

    try:
        last_timestamp = (
            float(last_time_str)
            if last_time_str
            else 0
        )

    except ValueError:
        last_timestamp = 0

    if (
        last_timestamp
        and (
            current_timestamp
            - last_timestamp
        )
        < HISTORY_INTERVAL_HOURS * 3600
    ):
        return

    index_str = read_state(
        HISTORY_INDEX_FILE
    )

    try:
        index = (
            int(index_str)
            if index_str
            else 0
        )

    except ValueError:
        index = 0

    if index >= len(
        KOZELETS_HISTORY_FACTS
    ):
        index = 0

    fact = (
        KOZELETS_HISTORY_FACTS[index]
    )

    text = (
        "📚 ІСТОРІЯ ТА КРАЄЗНАВСТВО КРАЮ\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"{fact}\n\n"
        "#Козелець #Остер "
        "#Бобровиця #Історія"
    )

    message_id = send_message(
        text
    )

    if message_id:
        write_state(
            HISTORY_INDEX_FILE,
            index + 1,
        )

        write_state(
            HISTORY_LAST_TIME_FILE,
            current_timestamp,
        )

        print(
            "📚 Історичний пост "
            "опубліковано."
        )


# =========================================================
# ІНФОРМАЦІЙНА ПАНЕЛЬ
# =========================================================

def build_dashboard_text():
    alarm = (
        read_state(
            ALERT_STATE_FILE
        ) == "1"
    )

    if alarm:
        alarm_text = (
            "🚨 ТРИВОГА "
            "в Чернігівській області!"
        )
    else:
        alarm_text = (
            "🟢 Немає активної "
            "тривоги"
        )

    weather = format_weather_short()

    radiation = check_radiation()

    power = check_power()

    now = datetime.now(
        TIMEZONE
    ).strftime(
        "%d.%m.%Y %H:%M"
    )

    text = (
        "📌 ІНФОРМАЦІЙНА ПАНЕЛЬ ГРОМАДИ\n"
        "Козелець • Остер • Бобровиця\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"

        f"{alarm_text}\n\n"

        f"🌤️ Погода: {weather}\n\n"

        f"⚡ Електропостачання:\n"
        f"{power}\n\n"

        f"☢️ Радіаційний фон:\n"
        f"{radiation}\n\n"

        "🌊 Моніторинг води:\n"
        f"{WATER_URL}\n\n"

        "⚡ Відключення:\n"
        f"{CHERNIHIV_OBLENERGO_URL}\n\n"

        "☢️ Радіологічна ситуація:\n"
        f"{UKR_HYDROMET_RAD_URL}\n\n"

        "━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 Оновлено: {now}\n\n"
        "🤖 Автоматичне оновлення "
        "кожні 5 хвилин."
    )

    return text


def update_live_dashboard():
    text = build_dashboard_text()

    msg = read_state(
        PINNED_MSG_ID_FILE
    )

    if msg:
        try:
            message_id = int(msg)

            if edit_message(
                message_id,
                text,
            ):
                print(
                    "📌 Панель оновлено."
                )

                # Переконуємося, що повідомлення
                # залишається закріпленим.
                pin_message(
                    message_id
                )

                return

        except Exception as exc:
            print(
                "Dashboard edit:",
                exc,
            )

    new_msg = send_message(
        text
    )

    if new_msg:
        write_state(
            PINNED_MSG_ID_FILE,
            new_msg,
        )

        pin_message(
            new_msg
        )

        print(
            "📌 Створено нову "
            "інформаційну панель."
        )


# =========================================================
# ДОДАТКОВИЙ ПОСТ ПРО ПОГОДУ
# =========================================================

def get_weather_state():
    return read_state(
        LAST_WEATHER_FILE
    )


def save_weather_state(value):
    write_state(
        LAST_WEATHER_FILE,
        value,
    )


def weather_change_key():
    data = get_weather()

    if not data:
        return ""

    return "|".join(
        [
            str(
                data.get(
                    "weather_code",
                    "",
                )
            ),
            str(
                data.get(
                    "temperature",
                    "",
                )
            ),
            str(
                data.get(
                    "wind_speed",
                    "",
                )
            ),
        ]
    )


# =========================================================
# ЛОГУВАННЯ СТАНУ
# =========================================================

def print_system_status():
    print("")
    print("=" * 60)
    print("📡 СТАН СИСТЕМИ")
    print("=" * 60)

    print(
        "BOT_TOKEN:",
        "OK" if BOT_TOKEN else "MISSING",
    )

    print(
        "CHANNEL:",
        "OK" if CHANNEL else "MISSING",
    )

    print(
        "UKRAINE_ALARM_API_KEY:",
        "OK"
        if UKRAINE_ALARM_API_KEY
        else "MISSING",
    )

    print(
        "TIME:",
        datetime.now(
            TIMEZONE
        ).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )

    print("=" * 60)
    print("")


# =========================================================
# ПЕРЕВІРКА КОНФІГУРАЦІЇ
# =========================================================

def validate_config():
    valid = True

    if not BOT_TOKEN:
        print(
            "❌ Не заданий BOT_TOKEN."
        )
        valid = False

    if not CHANNEL:
        print(
            "❌ Не заданий CHANNEL."
        )
        valid = False

    if not UKRAINE_ALARM_API_KEY:
        print(
            "⚠️ Не заданий "
            "UKRAINE_ALARM_API_KEY."
        )
        print(
            "⚠️ Тривоги не працюватимуть, "
            "поки Secret не буде доданий."
        )

    return valid


# =========================================================
# ОСНОВНИЙ ЗАПУСК
# =========================================================

def main():
    print("")
    print("=" * 60)
    print("🤖 KOZELETS ALARM BOT")
    print("=" * 60)

    print(
        datetime.now(
            TIMEZONE
        ).strftime(
            "%d.%m.%Y %H:%M:%S"
        )
    )

    print("=" * 60)

    if not validate_config():
        print(
            "❌ Конфігурація Telegram "
            "неповна."
        )

        # Не завершуємо відразу —
        # це дозволяє бачити помилки
        # у GitHub Actions.
        if not BOT_TOKEN or not CHANNEL:
            return

    # -----------------------------------------------------
    # 1. ТРИВОГА
    # -----------------------------------------------------

    try:
        check_alerts()

    except Exception as exc:
        print(
            "❌ Alerts error:",
            exc,
        )

    # -----------------------------------------------------
    # 2. ІНФОРМАЦІЙНА ПАНЕЛЬ
    # -----------------------------------------------------

    try:
        update_live_dashboard()

    except Exception as exc:
        print(
            "❌ Dashboard error:",
            exc,
        )

    # -----------------------------------------------------
    # 3. НОВИНИ
    # -----------------------------------------------------

    try:
        check_news()

    except Exception as exc:
        print(
            "❌ News error:",
            exc,
        )

    # -----------------------------------------------------
    # 4. ІСТОРІЯ
    # -----------------------------------------------------

    try:
        check_and_send_history_post()

    except Exception as exc:
        print(
            "❌ History error:",
            exc,
        )

    print("")
    print("=" * 60)
    print("✅ ЦИКЛ ЗАВЕРШЕНО")
    print("=" * 60)
    print("")


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
