import os
import html
import re
import hashlib
import requests
import xml.etree.ElementTree as ET

from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta


BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = os.environ.get("CHANNEL", "@Kozelets_Alarm")

NEWS_SEEN_FILE = "news_seen.txt"
ALERT_STATE_FILE = "alert_state.txt"
MAPA_STATE_FILE = "mapa_state.txt"

MAX_NEWS_AGE_HOURS = 3

KOZELETS_LAT = 50.913
KOZELETS_LON = 31.115
MAPA_RADIUS_KM = 100


# ============================================================
# НАЛАШТУВАННЯ ДЖЕРЕЛ
# ============================================================

NEWS_SOURCES = [

    # --------------------------------------------------------
    # СУСПІЛЬНЕ — НАЙВИЩИЙ ПРІОРИТЕТ
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CHELINE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ЧАС ЧЕРНІГІВСЬКИЙ
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # GOOGLE NEWS — ЗАГАЛЬНИЙ ПОШУК
    # --------------------------------------------------------

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

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

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

        print(
            "Telegram:",
            response.status_code
        )

        if not response.ok:
            print(
                "Помилка Telegram:",
                response.text
            )

        return response.ok

    except Exception as error:

        print(
            "Помилка Telegram:",
            error
        )

        return False


def send_telegram_photo(
    photo_url,
    caption
):

    if not BOT_TOKEN:
        print(
            "Помилка: BOT_TOKEN не заданий"
        )
        return False

    try:

        image_response = requests.get(
            photo_url,
            timeout=20,
            headers={
                "User-Agent":
                    "Mozilla/5.0"
            }
        )

        if not image_response.ok:
            return False

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendPhoto"
        )

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
                    image_response.headers.get(
                        "Content-Type",
                        "image/jpeg"
                    )
                )
            },
            timeout=30
        )

        print(
            "Telegram photo:",
            response.status_code
        )

        if not response.ok:
            print(
                "Помилка Telegram photo:",
                response.text
            )

        return response.ok

    except Exception as error:

        print(
            "Помилка відправки фото:",
            error
        )

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
        normalized.encode(
            "utf-8"
        )
    ).hexdigest()


def similarity(
    text1,
    text2
):

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
# ЗБЕРЕЖЕНІ НОВИНИ
# ============================================================

def load_seen_news():

    if not os.path.exists(
        NEWS_SEEN_FILE
    ):
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
# ОТРИМАННЯ ДАНИХ СТАТТІ
# ============================================================

def get_article_data(url):

    description = ""
    image_url = ""

    try:

        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36"
            }
        )

        if not response.ok:

            return (
                description,
                image_url
            )

        page = response.text

        # ----------------------------------------------------
        # OG DESCRIPTION
        # ----------------------------------------------------

        match = re.search(
            r'<meta[^>]+property=["\']'
            r'og:description["\'][^>]+'
            r'content=["\']([^"\']+)',
            page,
            re.IGNORECASE
        )

        if match:

            description = clean_text(
                match.group(1)
            )

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        if not description:

            match = re.search(
                r'<meta[^>]+name=["\']'
                r'description["\'][^>]+'
                r'content=["\']([^"\']+)',
                page,
                re.IGNORECASE
            )

            if match:

                description = clean_text(
                    match.group(1)
                )

        # ----------------------------------------------------
        # OG IMAGE
        # ----------------------------------------------------

        match = re.search(
            r'<meta[^>]+property=["\']'
            r'og:image["\'][^>]+'
            r'content=["\']([^"\']+)',
            page,
            re.IGNORECASE
        )

        if match:

            image_url = html.unescape(
                match.group(1)
            )

        # ----------------------------------------------------
        # TWITTER IMAGE
        # ----------------------------------------------------

        if not image_url:

            match = re.search(
                r'<meta[^>]+name=["\']'
                r'twitter:image["\'][^>]+'
                r'content=["\']([^"\']+)',
                page,
                re.IGNORECASE
            )

            if match:

                image_url = html.unescape(
                    match.group(1)
                )

    except Exception as error:

        print(
            "Помилка отримання статті:",
            error
        )

    return (
        description,
        image_url
    )


# ============================================================
# GOOGLE NEWS
# ============================================================

def get_google_news(
    source
):

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

def is_recent(
    date_string
):

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

def allowed_news(
    item
):

    title = normalize_text(
        item["title"]
    )

    category = item["category"]

    # --------------------------------------------------------
    # СПОРТ
    # --------------------------------------------------------

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
            "козелецька громада"
            not in title
        ):

            return False

    # --------------------------------------------------------
    # ЧЕРНІГІВ
    # --------------------------------------------------------

    if category == "🏙️ ЧЕРНІГІВ":

        if "чернігів" not in title:

            return False

    return True


# ============================================================
# ДЕДУПЛІКАЦІЯ
# ============================================================

def is_duplicate(
    item,
    published_items
):

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

    # --------------------------------------------------------
    # Перевірка по хешу
    # --------------------------------------------------------

    item_hash = make_hash(
        item_title
        + item_description
    )

    for existing in published_items:

        if existing["hash"] == item_hash:

            return True

    # --------------------------------------------------------
    # Перевірка схожості
    # --------------------------------------------------------

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

        # Дуже схожі заголовки
        if title_similarity >= 0.82:

            return True

        # Схожий заголовок + текст
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

    # --------------------------------------------------------
    # ПЕРВИННИЙ ФІЛЬТР
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # СПОЧАТКУ ОБРОБЛЯЄМО ДЖЕРЕЛА
    # З НАЙВИЩИМ ПРІОРИТЕТОМ
    # --------------------------------------------------------

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

        print(
            "Перевірка:",
            item["title"],
            "| пріоритет:",
            item["priority"]
        )

        # ----------------------------------------------------
        # ОТРИМУЄМО ТЕКСТ ТА КАРТИНКУ
        # ----------------------------------------------------

        article_text = ""
        image_url = ""

        article_text, image_url = (
            get_article_data(
                item["link"]
            )
        )

        if not article_text:

            article_text = clean_text(
                item.get(
                    "description",
                    ""
                )
            )

        # ----------------------------------------------------
        # ПЕРЕВІРЯЄМО ДУБЛІКАТ
        # ----------------------------------------------------

        temp_item = {
            "title": item["title"],
            "description": article_text,
            "hash": make_hash(
                item["title"]
                + article_text
            )
        }

        if is_duplicate(
            temp_item,
            published_items
        ):

            print(
                "⏭️ ДУБЛІКАТ:",
                item["title"]
            )

            seen.add(
                item["link"]
            )

            continue

        # ----------------------------------------------------
        # ОЧИЩЕННЯ ТЕКСТУ
        # ----------------------------------------------------

        article_text = re.sub(
            r"Читайте також.*",
            "",
            article_text,
            flags=re.IGNORECASE
        ).strip()

        if len(article_text) < 20:

            article_text = (
                "Подробиці новини "
                "уточнюються."
            )

        # ----------------------------------------------------
        # ОБМЕЖЕННЯ ДЛЯ TELEGRAM
        # ----------------------------------------------------

        article_text = article_text[:750]

        message = (
            f"{item['category']}\n\n"
            f"📰 {html.unescape(item['title'])}\n\n"
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

            published_items.append(
                temp_item
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

    save_seen_news(
        seen
    )

    print(
        "Нових новин опубліковано:",
        published
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


def save_alert_states(
    states
):

    with open(
        ALERT_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        for name, active in (
            states.items()
        ):

            file.write(
                f"{name}="
                f"{'true' if active else 'false'}\n"
            )


def check_neptun():

    old_states = (
        load_alert_states()
    )

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
                active_regions.add(
                    name
                )

        for item in data.get(
            "raions",
            []
        ):

            name = item.get(
                "name",
                ""
            )

            if name:
                active_districts.add(
                    name
                )

        checks = {

            "Чернігівська область":
                "Чернігівська область"
                in active_regions,

            "Чернігівський район":
                "Чернігівський район"
                in active_districts
        }

        new_states = (
            old_states.copy()
        )

        for name, active in (
            checks.items()
        ):

            old_active = (
                old_states.get(
                    name,
                    False
                )
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
                    f"🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
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


def save_mapa_state(
    active
):

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

    old_active = (
        load_mapa_state()
    )

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

        active = (
            len(threats) > 0
        )

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

                save_mapa_state(
                    True
                )

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

                save_mapa_state(
                    False
                )

        else:

            save_mapa_state(
                active
            )

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

    check_neptun()

    check_mapa()

    print(
        "=== Перевірку завершено ==="
    )


if __name__ == "__main__":

    main()
