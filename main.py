import os
import html
import re
import requests
import xml.etree.ElementTree as ET
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

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": CHANNEL,
                "caption": caption
            },
            files={
                "photo": requests.get(
                    photo_url,
                    timeout=20
                ).content
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
# НОВИНИ
# ============================================================

def load_seen_news():
    if not os.path.exists(NEWS_SEEN_FILE):
        return set()

    with open(NEWS_SEEN_FILE, "r", encoding="utf-8") as file:
        return set(
            line.strip()
            for line in file
            if line.strip()
        )


def save_seen_news(seen):
    with open(NEWS_SEEN_FILE, "w", encoding="utf-8") as file:
        for item in sorted(seen):
            file.write(item + "\n")


def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_article_data(url):
    """
    Отримує короткий опис та головне зображення
    зі сторінки новини.

    Посилання використовується тільки всередині бота
    і НЕ публікується в Telegram.
    """

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
            return description, image_url

        page = response.text

        # Опис новини
        description_match = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
            page,
            re.IGNORECASE
        )

        if not description_match:
            description_match = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
                page,
                re.IGNORECASE
            )

        if description_match:
            description = clean_text(
                description_match.group(1)
            )

        # Головне зображення
        image_match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            page,
            re.IGNORECASE
        )

        if image_match:
            image_url = html.unescape(
                image_match.group(1)
            )

        # Додатковий варіант пошуку картинки
        if not image_url:
            image_match = re.search(
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
                page,
                re.IGNORECASE
            )

            if image_match:
                image_url = html.unescape(
                    image_match.group(1)
                )

    except Exception as error:
        print(
            "Не вдалося отримати дані статті:",
            error
        )

    return description, image_url


def get_news():

    news_sources = [
        {
            "query": "Козелець Козелецька громада",
            "category": "📍 КОЗЕЛЕЦЬ"
        },
        {
            "query": "Чернігів Чернігівщина",
            "category": "🏙️ ЧЕРНІГІВЩИНА"
        },
        {
            "query": "Україна головні новини",
            "category": "🇺🇦 УКРАЇНА"
        },
        {
            "query": "війна Україна фронт",
            "category": "⚔️ ФРОНТ / ВІЙНА"
        }
    ]

    all_news = []

    for source in news_sources:

        query = source["query"]
        category = source["category"]

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
                continue

            root = ET.fromstring(response.text)

            for item in root.findall(".//item"):

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

                all_news.append({
                    "title": title,
                    "link": link,
                    "date": pub_date,
                    "description": description,
                    "category": category
                })

        except Exception as error:

            print(
                f"Помилка Google News [{category}]:",
                error
            )

    return all_news


def publish_news():

    seen = load_seen_news()
    news = get_news()

    now = datetime.now(timezone.utc)

    published = 0

    sports_words = [
        "футбол",
        "спорт",
        "матч",
        "чемпіонат",
        "баскетбол",
        "теніс",
        "хокей"
    ]

    for item in news:

        link = item["link"]

        if link in seen:
            continue

        try:

            pub_time = datetime.strptime(
                item["date"],
                "%a, %d %b %Y %H:%M:%S %Z"
            ).replace(
                tzinfo=timezone.utc
            )

            age = now - pub_time

            if age > timedelta(
                hours=MAX_NEWS_AGE_HOURS
            ):
                continue

            if age < timedelta(
                seconds=0
            ):
                continue

        except Exception:
            pass

        title_lower = item["title"].lower()

        if any(
            word in title_lower
            for word in sports_words
        ):
            continue

        print(
            "Обробка новини:",
            item["title"]
        )

        # Отримуємо короткий текст і картинку
        article_text, image_url = get_article_data(
            link
        )

        # Якщо сайт не дав опис —
        # використовуємо опис RSS
        if not article_text:
            article_text = clean_text(
                item.get("description", "")
            )

        # Прибираємо зайві службові фрази
        article_text = re.sub(
            r"Читайте також.*",
            "",
            article_text,
            flags=re.IGNORECASE
        ).strip()

        # Якщо текст дуже короткий,
        # залишаємо хоча б заголовок
        if len(article_text) < 20:
            article_text = (
                "Подробиці новини "
                "будуть уточнюватися."
            )

        # Telegram має обмеження на caption 1024 символи
        article_text = article_text[:750]

        message = (
            f"{item['category']}\n\n"
            f"📰 {html.unescape(item['title'])}\n\n"
            f"{article_text}"
        )

        success = False

        # Якщо є картинка — публікуємо з нею
        if image_url:

            success = send_telegram_photo(
                image_url,
                message[:1024]
            )

        # Якщо картинку отримати не вдалося —
        # публікуємо текстову новину
        if not success:

            success = send_telegram(
                message
            )

        if success:

            seen.add(link)
            published += 1

    save_seen_news(seen)

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

                name, state = line.strip().split(
                    "=",
                    1
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

            if active and not old_active:

                success = send_telegram(
                    f"🔴 ПОВІТРЯНА ТРИВОГА\n\n"
                    f"📍 {name}\n\n"
                    f"⚠️ Стежте за офіційними повідомленнями.\n"
                    f"ℹ️ Джерело: NEPTUN"
                )

                if success:
                    new_states[name] = True
                else:
                    print(
                        "⚠️ Тривогу не вдалося "
                        "відправити. Повторимо спробу."
                    )

            elif not active and old_active:

                success = send_telegram(
                    f"🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
                    f"📍 {name}\n\n"
                    f"ℹ️ Джерело: NEPTUN"
                )

                if success:
                    new_states[name] = False
                else:
                    print(
                        "⚠️ Відбій не вдалося "
                        "відправити. Повторимо спробу."
                    )

            else:

                new_states[name] = active

        save_alert_states(new_states)

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

            value = file.read().strip()

            return value == "true"

    except Exception:
        return False


def save_mapa_state(active):

    with open(
        MAPA_STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "true" if active else "false"
        )


def check_mapa():

    old_active = load_mapa_state()

    try:

        url = (
            "https://mapa.ua/api/v1/nearby"
        )

        params = {
            "lat": KOZELETS_LAT,
            "lon": KOZELETS_LON,
            "radius_km": MAPA_RADIUS_KM
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

        if active and not old_active:

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

        elif not active and old_active:

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

    check_neptun()

    check_mapa()

    print(
        "=== Перевірку завершено ==="
    )


if __name__ == "__main__":
    main()
