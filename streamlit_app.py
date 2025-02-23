import streamlit as st
import json
import os
from check_404 import (
    NOT_FOUND_JSON_PATH,
    update_not_found_list,
    load_not_found_data,
    main as run_check_404
)

st.title("404 Check Dashboard")

# -------------- JSONデータの読み込み --------------
data = load_not_found_data()
records = data["data"]  # [{ "url": ..., "parent": ..., "status": ... }, ...]

if "records_state" not in st.session_state:
    # セッションステートにロード
    st.session_state["records_state"] = records

def save_state_to_json():
    """セッションステート内のレコードをJSONに反映"""
    new_data = {"data": st.session_state["records_state"]}
    with open(NOT_FOUND_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

# -------------- 404リスト表示＆ステータス管理 --------------
st.subheader("Detected 404 Links")
if len(st.session_state["records_state"]) == 0:
    st.write("現在404は検出されていません。")
else:
    # テーブル表示する
    # 各行に対してステータスを選択できるようにする例
    updated_records = []
    for i, rec in enumerate(st.session_state["records_state"]):
        col1, col2, col3, col4 = st.columns([3,3,2,2])
        with col1:
            st.markdown(f"**URL**: {rec['url']}")
        with col2:
            st.write(f"From: {rec['parent']}")
        with col3:
            # Status のセレクトボックス例
            new_status = st.selectbox(
                label="Status",
                options=["open", "fixed", "ignore"],
                index=["open","fixed","ignore"].index(rec["status"]),
                key=f"select_{i}"
            )
            rec["status"] = new_status
        with col4:
            st.write("")  # スペーサ

        updated_records.append(rec)

    st.session_state["records_state"] = updated_records

    if st.button("Save Changes"):
        save_state_to_json()
        st.success("ステータスを保存しました。")

# -------------- 手動で再チェックボタン --------------
st.subheader("Run 404 Check Manually")
if st.button("Run 404 Check Now"):
    st.info("Checking... This may take a while.")
    run_check_404()
    # 再実行後にJSONを再読み込み
    st.session_state["records_state"] = load_not_found_data()["data"]
    st.success("再チェック完了しました。更新した404リストを反映しています。")
