import json
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

# =========================
# 設定
# =========================
CACHE_JSON = Path("kanto_images.json")
PREFS_KANTO = ["東京", "神奈川", "千葉", "埼玉", "茨城", "栃木", "群馬"]

# 表示用ラベル（順番や番号は気にしない）
RANK_LABELS = [
    "1位",
    "2位",
    "ベスト4",
    "ベスト4",
    "ベスト8",
    "ベスト8",
    "ベスト8",
    "ベスト8",
]

DEFAULT_LIMIT = 100  # 通常表示の上限


# =========================
# utility
# =========================
def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def json_mtime() -> float:
    """JSONの更新時刻（秒）。更新時にキャッシュを自動破棄するために使う"""
    return CACHE_JSON.stat().st_mtime if CACHE_JSON.exists() else 0.0


@st.cache_data(show_spinner=False)
def load_items(_mtime: float) -> list[dict]:
    """kanto_images.json を読み込んで新しい順に返す（表示専用）"""
    if not CACHE_JSON.exists():
        return []

    data = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    data.sort(key=lambda x: x.get("article_date", ""), reverse=True)
    return data


# =========================
# main app
# =========================
def main():
    st.set_page_config(page_title="関東シティリーグ Top8", layout="wide")

    st.title("関東シティリーグ Top8（見る専）")

    # ---- 注意書き ----
    st.info(
        "\n\n".join([
            "⚠️ 記事内に **Top8画像が存在しない店舗は表示されません**",
            "⚠️ 表示が古い場合は、**ページ再読み込み（R / F5）** をしてください",
            "✅ 本ページは **ポケカブックさん** から **直近14日分** の **関東** のシティリーグ記事を抽出しています",
            "✅ データ更新は **1日1回 自動で行われます**",
        ])
    )

    # ---- JSONロード ----
    items = load_items(json_mtime())

    if not items:
        st.warning("kanto_images.json が見つからないか、空です。")
        st.info("まずローカルで update_json.py を実行して JSON を作ってください。")
        return

    # ---- 表示期間：直近14日 ----
    today = date.today()
    since = today - timedelta(days=14)
    until = today

    # JSON内の最新記事日付
    try:
        latest_article_date = max(
            parse_date(x["article_date"])
            for x in items
            if x.get("article_date")
        )
        latest_str = latest_article_date.strftime("%Y-%m-%d")
    except ValueError:
        latest_str = "不明"

    st.caption(
        f"表示期間：{since.strftime('%Y-%m-%d')} 〜 {until.strftime('%Y-%m-%d')}（直近14日）｜"
        f"記事の最新確認日：{latest_str}"
    )

    # =========================
    # sidebar（絞り込み）
    # =========================
    st.sidebar.header("絞り込み")

    pref_selected = st.sidebar.multiselect(
        "都道府県",
        options=PREFS_KANTO,
        default=PREFS_KANTO,
    )

    show_all = st.sidebar.checkbox(
        f"すべて表示（通常は最大{DEFAULT_LIMIT}件）",
        value=False
    )

    # =========================
    # filter
    # =========================
    def in_range(d: date) -> bool:
        return since <= d <= until

    filtered: list[dict] = []
    for x in items:
        if x.get("pref") not in pref_selected:
            continue
        if not x.get("article_date"):
            continue

        d = parse_date(x["article_date"])
        if not in_range(d):
            continue

        filtered.append(x)

    if not show_all:
        filtered = filtered[:DEFAULT_LIMIT]

    # =========================
    # summary
    # =========================
    st.subheader("サマリー")
    limit_note = "（全件表示）" if show_all else f"（上限{DEFAULT_LIMIT}件）"
    st.markdown(
        f"""
**表示件数**：{len(filtered)} 件 {limit_note}  
**対象期間**：{since.strftime('%Y-%m-%d')} 〜 {until.strftime('%Y-%m-%d')}
"""
    )

    st.divider()

    # =========================
    # render
    # =========================
    for x in filtered:
        title = x.get("title", "（無題）")
        page = x.get("page", "")
        d = x.get("article_date", "")
        imgs = (x.get("images_top8") or [])[:8]

        header = f"{title}｜{d}"

        with st.expander(header, expanded=False):
            st.markdown(f"**ページ：** {page}")

            if not imgs:
                st.info("画像がありません。")
                continue

            left, right = st.columns(2)
            for i, url in enumerate(imgs):
                label = RANK_LABELS[i] if i < len(RANK_LABELS) else ""
                target = left if i % 2 == 0 else right
                if label:
                    target.markdown(f"**{label}**")
                target.image(url, use_container_width=True)


if __name__ == "__main__":
    main()
