import os
import json
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
import openai

# ===== НАСТРОЙКИ =====

TAGS = [
    "black-metal",
    "atmospheric-black-metal",
    "post-black-metal",
    "blackgaze",
    "depressive-black-metal"
]

OUTPUT_JSON = "output/playwright_releases.json"
OUTPUT_MD = "output/digest.md"
MAX_RELEASES = 20

openai.api_key = os.environ.get("OPENAI_API_KEY", "sk-xxx")


# ===== СБОР РЕЛИЗОВ ЧЕРЕЗ PLAYWRIGHT =====

def get_discover_releases(tag: str) -> list:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ))
        page = context.new_page()

        page_url = f"https://bandcamp.com/discover/{tag}"
        print(f"[INFO] Fetching: {page_url}")
        page.goto(page_url, timeout=60000)

        try:
            page.wait_for_selector(".discover-result", timeout=60000)
        except Exception as e:
            print(f"[WARN] Timeout while waiting for .discover-result on tag '{tag}': {e}")
            Path("output").mkdir(parents=True, exist_ok=True)
            page.screenshot(path=f"output/screenshot_{tag}.png")
            return []

        items = page.query_selector_all(".discover-result")
        results = []

        for item in items:
            title_el = item.query_selector(".heading")
            link_el = item.query_selector("a.item-link")
            artist_el = item.query_selector(".itemsubtext")
            genre_el = item.query_selector(".tags")

            title = title_el.inner_text().strip() if title_el else None
            album_url = link_el.get_attribute("href") if link_el else None
            artist = artist_el.inner_text().strip() if artist_el else ""
            genre = genre_el.inner_text().strip() if genre_el else ""

            if not (title and album_url):
                print(f"[WARN] Skipping item with missing data: title={title}, url={album_url}")
                continue

            results.append({
                "title": title,
                "artist": artist,
                "url": album_url,
                "tag": tag,
                "genre": genre,
                "fetched_at": datetime.utcnow().isoformat()
            })

        browser.close()
        return results


# ===== GPT-4o: СОЗДАНИЕ ДАЙДЖЕСТА =====

def ask_gpt_digest(releases: list) -> str:
    system_prompt = {
        "role": "system",
        "content": (
            "Ты музыкальный редактор блэк-метал дайджеста. Пиши на русском языке. "
            "Тебе нужно выбрать ровно 5 лучших релизов из списка, который тебе пришлют. "
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


# ===== СОХРАНЕНИЕ =====

def save_json(data: list, path: str):
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_markdown(text: str, path: str):
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ===== ОСНОВНОЙ БЛОК =====

def main():
    all_releases = []
    seen_urls = set()

    for tag in TAGS:
        releases = get_discover_releases(tag)
        for r in releases:
            if r["url"] not in seen_urls:
                all_releases.append(r)
                seen_urls.add(r["url"])

    print(f"[INFO] Всего уникальных релизов собрано: {len(all_releases)}")
    save_json(all_releases, OUTPUT_JSON)

    filtered = all_releases[:MAX_RELEASES]

    if not filtered:
        print("[INFO] Нечего отправлять в GPT")
        save_markdown("# Дайджест\n\nНичего не найдено", OUTPUT_MD)
        return

    digest_md = ask_gpt_digest(filtered)
    save_markdown(digest_md, OUTPUT_MD)
    print(f"[DONE] Дайджест сохранён в {OUTPUT_MD}")


if __name__ == "__main__":
    main()
