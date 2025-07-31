import os
import json
import openai
import feedparser
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


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def fetch_releases_from_rss(tag: str) -> list:
    """
    Получает список релизов по RSS для заданного тега
    """
    url = f"https://bandcamp.com/tag/{tag}?sort_field=date&format=rss"
    print(f"[INFO] Fetching RSS: {url}")
    feed = feedparser.parse(url)

    releases = []
    for entry in feed.entries:
        # Преобразуем дату публикации
        try:
            published = datetime(*entry.published_parsed[:6])
        except Exception:
            continue

        if datetime.utcnow() - published > timedelta(days=DAYS_LIMIT):
            continue

        releases.append({
            "title": entry.title,
            "artist": entry.author if "author" in entry else "Unknown Artist",
            "url": entry.link,
            "release_date": published.strftime("%Y-%m-%d"),
            "description": entry.summary if "summary" in entry else ""
        })

    return releases


def ask_gpt_digest(releases: list) -> str:
    """
    Отдаём релизы в GPT и получаем готовый markdown
    """
    system_prompt = {
        "role": "system",
        "content": (
            "Ты музыкальный редактор блэк-метал дайджеста. Пиши на русском языке. "
            "Тебе нужно выбрать 5 лучших релизов из списка, который тебе пришлют. "
            "Ты не просто описываешь — ты передаёшь атмосферу. "
            "Можно материться, если это помогает выразить эмоцию. "
            "Не пиши слишком много, но и не скупись на детали. "
            "Старайся находить малоизвестные группы, но если релиз известный, упоминай это. "
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
    Сохраняем результат в markdown-файл
    """
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ===== ОСНОВНОЙ БЛОК =====

def main():
    all_releases = {}

    for tag in TAGS:
        releases = fetch_releases_from_rss(tag)
        for r in releases:
            all_releases[r["url"]] = r  # защита от дубликатов

    # Сортируем по дате и берём первые MAX_RELEASES
    unique_releases = sorted(
        all_releases.values(),
        key=lambda r: r["release_date"],
        reverse=True
    )[:MAX_RELEASES]

    if not unique_releases:
        save_markdown("# Дайджест\n\nК сожалению, новых релизов не найдено.", OUTPUT_FILE)
        print("[INFO] Нет подходящих релизов.")
        return

    digest = ask_gpt_digest(unique_releases)
    save_markdown(digest, OUTPUT_FILE)
    print(f"[DONE] Дайджест сохранён в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
