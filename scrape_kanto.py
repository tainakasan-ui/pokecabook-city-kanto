import sys
import asyncio
import re
import time
from datetime import date
from urllib.parse import urljoin

# Windows + Playwright の asyncio policy 対策
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from playwright.sync_api import sync_playwright

LIST_URL = "https://pokecabook.com/archives/category/tournament/city-league"
KANTO_PREFS = {"東京", "神奈川", "千葉", "埼玉", "茨城", "栃木", "群馬"}

PREF_RE = re.compile(r"（([^）]+)）")
DATE_DOT_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
DATE_DASH_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_yyyymmdd_dot(s: str):
    if not s:
        return None
    m = DATE_DOT_RE.search(s)
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    return date(y, mo, d)


def parse_yyyymmdd_dash(s: str):
    if not s:
        return None
    m = DATE_DASH_RE.search(s)
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    return date(y, mo, d)


def parse_article_date_from_article(page) -> date | None:
    """
    記事ページから日付を取る
    - time[datetime] があればそれを優先
    - なければ本文テキストから yyyy.mm.dd / yyyy-mm-dd を探す
    """
    time_el = page.locator("time").first
    if time_el.count() > 0:
        dt_attr = time_el.get_attribute("datetime")
        if dt_attr:
            d = parse_yyyymmdd_dash(dt_attr) or parse_yyyymmdd_dot(dt_attr)
            if d:
                return d
        txt = (time_el.inner_text() or "").strip()
        d = parse_yyyymmdd_dot(txt) or parse_yyyymmdd_dash(txt)
        if d:
            return d

    body_txt = page.locator("body").inner_text() or ""
    return parse_yyyymmdd_dot(body_txt) or parse_yyyymmdd_dash(body_txt)


def extract_imgs_until_next_heading(heading):
    """
    見出し（h2/h4）の次から、次の見出し（h2/h4）までに含まれる img の src を拾う。
    ※ 2/1記事は店舗見出しが h2 なので、h4固定だと拾えないため一般化。
    """
    return heading.evaluate(
        """(h) => {
            const OUT = [];
            const isStopHeading = (el) => {
                if (!el || !el.tagName) return false;
                const t = el.tagName.toLowerCase();
                return (t === 'h2' || t === 'h4');
            };

            let el = h.nextElementSibling;
            while (el) {
                if (isStopHeading(el)) break;

                const imgs = el.querySelectorAll('img');
                for (const img of imgs) {
                    const src =
                        img.getAttribute('data-src') ||
                        img.getAttribute('data-lazy-src') ||
                        img.getAttribute('data-original') ||
                        img.currentSrc ||
                        img.src;
                    if (src) OUT.push(src);
                }

                el = el.nextElementSibling;
            }
            return OUT;
        }"""
    )


def clean_image_urls(urls):
    """
    画像URLを最低限きれいにして重複排除。
    ※ 拡張子縛りはしない（pokemon-card.com 側はクエリ付き/拡張子無しの可能性がある）
    """
    cleaned = []
    for u in urls:
        if not u:
            continue
        u = u.strip()
        if u.startswith("data:"):
            continue
        if not (u.startswith("http://") or u.startswith("https://")):
            continue
        cleaned.append(u)

    seen = set()
    out = []
    for u in cleaned:
        key = u.split("?", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def collect_article_urls_from_list(page):
    """
    一覧ページから記事URLを集める（ベスト16デッキまとめ を含む /archives/ リンク）
    """
    urls = []
    links = page.locator('a[href*="/archives/"]:has-text("ベスト16デッキまとめ")')
    n = links.count()

    for i in range(n):
        a = links.nth(i)
        href = a.get_attribute("href") or ""
        if not href:
            continue
        urls.append(urljoin(page.url, href))

    seen = set()
    uniq = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


def scrape_kanto_top8(
    since: date,
    max_list_pages: int | None = 3,
    polite_sleep: float = 0.4,
):
    """
    一覧→記事へ辿り、記事内の見出し（h2/h4）ブロックから関東だけTop8画像を収集

    返り値：
      - results: 画像が取れた店舗レコードのリスト
      - latest_seen: 記事として見に行けた最新の日付（画像が無くても更新される）
    """
    results = []
    latest_seen: date | None = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(30000)

        list_url = LIST_URL
        list_page_idx = 0
        article_urls_all = []

        # 一覧ページを数ページ分集める
        while True:
            list_page_idx += 1
            if max_list_pages is not None and list_page_idx > max_list_pages:
                break

            page.goto(list_url, wait_until="networkidle")
            time.sleep(polite_sleep)

            for u in collect_article_urls_from_list(page):
                if u not in article_urls_all:
                    article_urls_all.append(u)

            next_link = page.locator('a:has-text("次のページ"), a:has-text("次へ")').first
            if next_link.count() == 0:
                break
            next_href = next_link.get_attribute("href") or ""
            if not next_href:
                break
            list_url = urljoin(page.url, next_href)

        dup_check = set()

        for article_url in article_urls_all:
            page.goto(article_url, wait_until="networkidle")
            time.sleep(polite_sleep)

            article_date = parse_article_date_from_article(page)
            if article_date is None:
                continue

            # ★「見に行けた最新日付」を更新（画像が取れなくても更新）
            if latest_seen is None or article_date > latest_seen:
                latest_seen = article_date

            # sinceより古い記事はスキップ（順番が混ざる可能性があるので break しない）
            if article_date < since:
                continue

            # ★ここが肝：h2/h4 両方見る
            headings = page.locator("h2, h4")

            for j in range(headings.count()):
                text_h = (headings.nth(j).inner_text() or "").strip()
                m = PREF_RE.search(text_h)
                if not m:
                    continue

                pref = m.group(1).strip()
                if pref not in KANTO_PREFS:
                    continue

                imgs = clean_image_urls(extract_imgs_until_next_heading(headings.nth(j)))
                if not imgs:
                    continue

                top8 = imgs[:8]

                k = (article_url, text_h)
                is_dup = k in dup_check
                dup_check.add(k)

                results.append(
                    {
                        "article_date": article_date.isoformat(),
                        "page": article_url,
                        "title": text_h,
                        "pref": pref,
                        "images_top8": top8,
                        "images_found": len(imgs),
                        "dup_same_page": is_dup,
                    }
                )

        browser.close()

    return results, latest_seen
