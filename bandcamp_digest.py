import os
import json
import openai
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ===== НАСТРОЙКИ =====

TAGS = [
    "black-metal",
    "atmospheric-black-metal",
    "post-black-metal",
    "blackgaze",
    "depressive-black-metal"
]

DAYS_LIMIT = 7
MAX_RELEASES = 20
OUTPUT_FILE = "output/digest.md"

openai.api_key = os.environ["OPENAI_API_KEY"]

# ===== ЗАПРОС В DISCOVER API =====

def fetch_bandcamp_releases(tag: str, page: int = 1) -> list:
    """
    Запрашивает релизы с Bandcamp Discover API по тегу и возвращает список
    """
    url = "https://bandcamp.com/api/discover/1/discover_web"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "filters": {
            "tag": tag
        },
        "sort": "date",
        "page": page
    }

    print(f"[INFO] Fetching tag '{tag}' page {page}...")
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()

    data = resp.json()
    items = data.get("items", [])
    releases = []

    for item in items:
        if "tralbum_title" not in item or not item.get("tralbum_url"):
            continue

        # Пример даты: "2024-11-18T00:00:00Z"
        pubdate = item.get("publish_date", "")
        try:
            dt = datetime.strptime(pubdate[:10], "%Y-%m-%d")
            if datetime.utcnow() - dt > timedelta(days=DAYS_LIMIT):
                continue
        except Exception:
            continue

        releases.append({
            "title": item.get("tralbum_title"),
            "artist": item.get("artist"),
            "url": item.get("tralbum_url"),
            "release_date": dt.strftime("%Y-%m-%d"),
            "description": item.get("genre") or ""  # можно будет потом дополнить
        })

    return releases


# ===== GPT-4o: СОЗДАНИЕ ДАЙДЖЕСТА =====

def ask_gpt_digest(releases: list) -> str:
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
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ===== ОСНОВНОЙ БЛОК =====

def main():
    all_releases = {}

    for tag in TAGS:
        releases = fetch_bandcamp_releases(tag)
        for r in releases:
            all_releases[r["url"]] = r  # убираем дубликаты

        if len(all_releases) >= MAX_RELEASES:
            break

    releases = list(all_releases.values())[:MAX_RELEASES]
    print(f"[INFO] Найдено релизов: {len(releases)}")

    if not releases:
        save_markdown("# Дайджест\n\nНичего не найдено за последние дни.", OUTPUT_FILE)
        return

    digest = ask_gpt_digest(releases)
    save_markdown(digest, OUTPUT_FILE)
    print(f"[DONE] Дайджест сохранён в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
