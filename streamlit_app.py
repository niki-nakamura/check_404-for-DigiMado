import streamlit as st
import requests
import os
from scripts.check_404 import (
    get_all_urls_from_sitemaps,
    check_404_urls,
    send_teams_notification,
    MAIN_SITEMAP_URL
)

st.title("404 Check Dashboard")

if "last_result" not in st.session_state:
    st.session_state["last_result"] = []

TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")
if not TEAMS_WEBHOOK_URL:
    st.warning("環境変数 TEAMS_WEBHOOK_URL が設定されていません。Teams通知ができません。")

if st.button("Run 404 Check"):
    with st.spinner("Checking..."):
        all_urls = get_all_urls_from_sitemaps(MAIN_SITEMAP_URL)
        not_found_urls = check_404_urls(all_urls)
        if not not_found_urls:
            message = "【404チェック結果】\n404は検出されませんでした。"
        else:
            message = "【404チェック結果】\n以下のURLが404でした:\n" + "\n".join(not_found_urls)

        # 結果をStreamlitに表示
        st.session_state["last_result"] = not_found_urls
        if not_found_urls:
            st.error(f"{len(not_found_urls)}件の404を検出")
        else:
            st.success("404は検出されませんでした")

        # Teams通知
        if TEAMS_WEBHOOK_URL:
            send_teams_notification(message)

st.subheader("Last Check Result")
if st.session_state["last_result"]:
    st.write("以下のURLが404でした:")
    for url in st.session_state["last_result"]:
        st.write(url)
else:
    st.write("まだチェックを実行していません。")
