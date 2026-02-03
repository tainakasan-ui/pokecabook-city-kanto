import json
from datetime import date, timedelta
from pathlib import Path

from scrape_kanto import scrape_kanto_top8

BASE_DIR = Path(__file__).resolve().parent
CACHE_JSON = BASE_DIR / "kanto_images.json"


def main():
    since = date.today() - timedelta(days=14)

    items, latest_seen = scrape_kanto_top8(since=since, max_list_pages=3)

    CACHE_JSON.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    latest_items = max((x.get("article_date", "") for x in items), default="(none)")
    print(f"updated {len(items)} items")
    print(f"latest_seen_article_date: {latest_seen.isoformat() if latest_seen else '(none)'}")
    print(f"latest_items_date: {latest_items}")


if __name__ == "__main__":
    main()
