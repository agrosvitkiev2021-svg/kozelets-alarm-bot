import os
import html
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta


BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = os.environ.get("CHANNEL", "@Kozelets_Alarm")

NEWS_SEEN_FILE = "news_seen.txt"
ALERT_STATE_FILE = "alert_state.txt"

MAX_NEWS_AGE_HOURS = 2

BASE_URL = "https://neptun.in.ua/api/v1"

REGIONS = {
    "Чернігівська область": "cernigivska-oblast",
    "Чернігівський район": "cernigivskii-raion"
}


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
        return response.ok

    except Exception as error:
        print("Помилка Telegram:", error)
        return False


def load_seen_news():
    if not os.path.exists(NEWS_SEEN_FILE):
        return set()

    with open(NEWS_SEEN_FILE, "r", encoding="utf-8") as file:
        return set(line.strip() for line in file if line.strip())


def save_seen_news(seen):
    with open(NEWS_SEEN_FILE, "w", encoding="utf-8") as file:
        for item in sorted(seen):
            file.write(item + "\n")


def get_news():
    queries = [
        "Козелець Козелецька громада",
        "Чернігів Чернігівщина"
    ]

    all_news = []

    for query in queries:
        url = (
            "https://news.google.com/rss/search?"
            f"q={requests.utils.quote(query)}"
            "&hl=uk&gl=UA&ceid=UA:uk"
        )

        try:
            response = requests.get(url, timeout=20)
            print("Google News:", response.status_code)

            if not response.ok:
                continue

            root = ET.fromstring(response.text)

            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")

                if not title or not link:
                    continue

                all_news.append({
                    "title": title,
                    "link": link,
                    "date": pub_date
                })

        except Exception as error:
            print("Помилка Google News:", error)

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
            ).replace(tzinfo=timezone.utc)

            if now - pub_time > timedelta(hours=MAX_NEWS_AGE_HOURS):
                continue

        except Exception:
            pass

        title_lower = item["title"].lower()

        if any(word in title_lower for word in sports_words):
            continue

        if "козелець" in title_lower or "ко́зелець" in title_lower:
            category = "📍 КОЗЕЛЕЦЬ"
        elif "черніг" in title_lower:
            category = "🏙️ ЧЕРНІГІВ"
        else:
            continue

        message = (
            f"{category}\n\n"
            f"📰 {html.unescape(item['title'])}\n\n"
            f"🔗 {item['link']}"
        )

        if send_telegram(message):
            seen.add(link)
            published += 1

    save_seen_news(seen)

    print("Нових новин опубліковано:", published)


def load_alert_states():
    states = {}

    if not os.path.exists(ALERT_STATE_FILE):
        return states

    with open(ALERT_STATE_FILE, "r", encoding="utf-8") as file:
        for line in file:
            if "=" in line:
                name, state = line.strip().split("=", 1)
                states[name] = state == "true"

    return states


def save_alert_states(states):
    with open(ALERT_STATE_FILE, "w", encoding="utf-8") as file:
        for name, active in states.items():
            file.write(f"{name}={'true' if active else 'false'}\n")


def check_alerts():
    old_states = load_alert_states()

    try:
        url = "https://neptun.in.ua/api/v1/alerts"
        response = requests.get(url, timeout=20)

        print("NEPTUN API:", response.status_code)

        if not response.ok:
            print("Помилка NEPTUN:", response.text)
            return

        data = response.json()

        active_regions = set()
        active_districts = set()

        for item in data.get("oblasts", []):
            name = item.get("name", "")
            if name:
                active_regions.add(name)

        for item in data.get("raions", []):
            name = item.get("name", "")
            if name:
                active_districts.add(name)

        checks = {
            "Чернігівська область": "Чернігівська область" in active_regions,
            "Чернігівський район": "Чернігівський район" in active_districts
        }

        for name, active in checks.items():

            old_active = old_states.get(name, False)

            print(name, "активна:", active)

            if active and not old_active:
                send_telegram(
                    f"🔴 ПОВІТРЯНА ТРИВОГА\n\n"
                    f"📍 {name}\n\n"
                    f"⚠️ Стежте за офіційними повідомленнями.\n"
                    f"ℹ️ Дані: NEPTUN"
                )

            elif not active and old_active:
                send_telegram(
                    f"🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ\n\n"
                    f"📍 {name}\n\n"
                    f"ℹ️ Дані: NEPTUN"
                )

        save_alert_states(checks)

    except Exception as error:
        print("Помилка перевірки тривоги:", error)

def main():
    print("=== Перевірка Козелець Alarm ===")

    publish_news()
    check_alerts()

    print("=== Перевірку завершено ===")


if __name__ == "__main__":
    main()
