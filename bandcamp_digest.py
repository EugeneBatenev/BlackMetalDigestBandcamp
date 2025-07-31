import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path
import openai

# ===== НАСТРОЙКИ =====

TAGS = [
    "black-metal",
    "atmospheric-black-metal",
    "post-black-metal",
    "blackgaze",
    "depressive-black-metal"
]

DAYS_LIMIT = 7
MIN_TRACKS = 4
MAX_RELEASES = 15
OUTPUT_FILE = "output/digest.md"

openai.api_key = os.environ["OPENAI_API_KEY"]


def fetch_bandcamp_tag_page(tag: str) -> str:
    """
    Получаем HTML по тегу с Bandcamp (с таймаутом и защитой)
    """
    url = f"https://bandcamp.com/tag/{tag}?sort_field=date"
    print(f"[INFO] Fetching: {url}")
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.text


def parse_releases(html: str) -> list:
    """
    Извлекаем (название, url) из страницы тега
    """
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("li", class_="item")
    releases = []

    for item in items:
        link = item.find("a", class_="item-link")
        if link:
            url = link["href"]
            title = link.text.strip()
            releases.append((title, url))
    return releases


def fetch_release_info(url: str) -> dict:
    """
    Заходим на страницу релиза и собираем данные
    """
    print(f"[INFO] Checking: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[WARN] Request failed for {url}: {e}")
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    try:
        title = soup.find("meta", property="og:title")["content"]
        artist = soup.find("meta", property="og:site_name")["content"]
        release_date_tag = soup.find("meta", itemprop="datePublished")
        release_date = release_date_tag["content"] if release_date_tag else "unknown"
        track_list = soup.select(".track_list .title")
        track_count = len(track_list)
        desc_tag = soup.select_one(".tralbum-about")
        description = desc_tag.get_text(strip=True) if desc_tag else ""
        return {
            "title": title,
            "artist": artist,
            "url": url,
            "release_date": release_date,
            "track_count": track_count,
            "description": description
        }
    except Exception as e:
        print(f"[WARN] Failed to parse {url}: {e}")
        return {}


def is_recent(release_date: str) -> bool:
    """
    Проверяет, не старше ли релиз X дней
    """
    try:
        dt = datetime.strptime(release_date, "%Y-%m-%d")
        return datetime.utcnow() - dt <= timedelta(days=DAYS_LIMIT)
    except Exception:
        return False


def ask_gpt_digest(releases: list) -> str:
    """
    Отдаём релизы в GPT-4o и получаем готовый markdown
    """
    system_prompt = {
        "role": "system",
        "content": (
            "Ты музыкальный редактор блэк-метал дайджеста. Пиши на русском языке. "
            "Тебе нужно выбрать 5 лучших релизов из списка, который тебе пришлют. "
            "Ты не просто описываешь — ты передаёшь атмосферу. "
            "Можно материться, если это помогает выразить эмоцию. "
            "Сравнивай релизы с другими известными группами (если есть сходство), "
            "упоминай настроение, качество звучания, тематику, вокал. "
            "Пиши коротко, сочно, и как будто ты говоришь с человеком, который шарит. "
            "Результат выдай в формате markdown. Название релиза — это заголовок уровня 2, ниже — краткое описание."
        )
    }

    user_prompt = {
        "role": "user",
        "content": f"Вот список релизов в JSON:\n{json.dumps(releases, indent=2, ensure_ascii=False)}"
    }

    print("[GPT] Запрашиваем дайджест у GPT-4o...")

    completion = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[system_prompt, user_prompt],
        temperature=0.9,
        max_tokens=1200,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.2
    )

    return completion["choices"][0]["message"]["content"]


def save_markdown(text: str, path: str):
    """
    Сохраняем результат в файл
    """
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    all_releases = {}

    for tag in TAGS:
        try:
            html = fetch_bandcamp_tag_page(tag)
        except Exception as e:
            print(f"[WARN] Failed to fetch tag page for {tag}: {e}")
            continue

        for _, url in parse_releases(html):
            if url in all_releases:
                continue

            info = fetch_release_info(url)
            if not info:
                continue
            if not is_recent(info["release_date"]):
                continue
            if info["track_count"] < MIN_TRACKS:
                continue
            if len(info["description"].strip()) < 30:
                continue  # пустые или бесполезные описания

            all_releases[url] = info

    # Сортируем релизы по дате
    releases = sorted(
        all_releases.values(),
        key=lambda r: r.get("release_date", "1900-01-01"),
        reverse=True
    )

    if not releases:
        save_markdown("# Дайджест\n\nК сожалению, подходящих релизов не найдено.", OUTPUT_FILE)
        return

    # Ограничиваем количество перед отправкой в GPT
    digest = ask_gpt_digest(releases[:MAX_RELEASES])
    save_markdown(digest, OUTPUT_FILE)
    print(f"[DONE] Дайджест сохранён в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
