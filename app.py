import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

# =========================
# 設定
# =========================
CACHE_JSON = Path("kanto_images.json")
PREFS_KANTO = ["東京", "神奈川", "千葉", "埼玉", "茨城", "栃木", "群馬"]

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

DEFAULT_LIMIT = 100  # 通常表示の上限（重くならないため）


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

    # ---- sidebar ----
    st.sidebar.header("操作 / 絞り込み")

    # ★手動リロード（キャッシュを消して読み直す）
    # これで「古いの掴んでる？」をユーザー側で自力復旧できる
    if st.sidebar.button("データを再読み込み（重い時あり）"):
        st.cache_data.clear()
        st.rerun()

    pref_selected = st.sidebar.multiselect(
        "都道府県",
        options=PREFS_KANTO,
        default=PREFS_KANTO,
    )

    show_all = st.sidebar.checkbox(
        f"すべて表示（通常は最大{DEFAULT_LIMIT}件）",
        value=False
    )

    # ---- 注意書き（文ごとに改行）----
    st.info(
        "\n\n".join([
            "🔄 **データを再読み込み**：ページを開いた直後は古いデータが表示されることがあります。**開いたら一度押すのがおすすめです。**",
            "⚠️ 記事内に **Top8画像が存在しない店舗は表示されません**",
            "✅ 本ページは **ポケカブックさん** から **直近14日分** の **関東** のシティリーグ記事を抽出しています",
            "✅ データ更新は **1日1回 自動で行われます**",
        ])
    )

    # ---- JSONロード ----
    mtime = json_mtime()
    items = load_items(mtime)

    if not items:
        st.warning("kanto_images.json が見つからないか、空です。")
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

    # ★JSON最終更新（mtime表示）
    # ※Streamlit Cloud はUTCで動くことが多いので、表示はJSTに寄せる
    jst = timezone(timedelta(hours=9))
    json_updated_str = (
        datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone(jst).strftime("%Y-%m-%d %H:%M:%S JST")
        if mtime > 0 else "不明"
    )

    st.caption(
        f"表示期間：{since.strftime('%Y-%m-%d')} 〜 {until.strftime('%Y-%m-%d')}（直近14日）｜"
        f"記事の最新確認日：{latest_str}｜"
        f"JSON最終更新：{json_updated_str}"
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

        header = f"{title}（{x.get('pref','')}）｜{d}"

        with st.expander(header, expanded=False):
            st.markdown(f"**ページ：** {page}")

            if not imgs:
                st.info("画像がありません。")
                continue

            # ★スマホでも順番が崩れないように「行」で左右表示（(0,1),(2,3)...）
            for i in range(0, len(imgs), 2):
                col_left, col_right = st.columns(2)

                url_left = imgs[i]
                label_left = RANK_LABELS[i] if i < len(RANK_LABELS) else ""
                if label_left:
                    col_left.markdown(f"**{label_left}**")
                col_left.image(url_left, use_container_width=True)

                if i + 1 < len(imgs):
                    url_right = imgs[i + 1]
                    label_right = RANK_LABELS[i + 1] if (i + 1) < len(RANK_LABELS) else ""
                    if label_right:
                        col_right.markdown(f"**{label_right}**")
                    col_right.image(url_right, use_container_width=True)


if __name__ == "__main__":
    main()