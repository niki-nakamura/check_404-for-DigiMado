import streamlit as st
import json
import os

# こちらが重要: 「from scripts.check_404 import ...」 と書く
# check_404.py が scripts/ フォルダ内にあるため
from scripts.check_404 import (
    NOT_FOUND_JSON_PATH,
    load_not_found_data,
    update_not_found_list,
    main as run_check_404
)

st.title("404 Check Dashboard")

data = load_not_found_data()
records = data["data"]  # [{ "url": ..., "parent": ..., "status": ... }, ...]

if "records_state" not in st.session_state:
    st.session_state["records_state"] = records

def save_state_to_json():
    new_data = {"data": st.session_state["records_state"]}
    os.makedirs(os.path.dirname(NOT_FOUND_JSON_PATH), exist_ok=True)
    with open(NOT_FOUND_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

st.subheader("Detected 404 Links")
if len(st.session_state["records_state"]) == 0:
    st.write("現在404は検出されていません。")
else:
    updated_records = []
    for i, rec in enumerate(st.session_state["records_state"]):
        col1, col2, col3, col4 = st.columns([3,3,2,2])
        with col1:
            st.markdown(f"**URL**: {rec['url']}")
        with col2:
            if rec["parent"] == "SELF":
                st.write("From: (article page itself)")
            else:
                st.write(f"From: {rec['parent']}")
        with col3:
            new_status = st.selectbox(
                label="Status",
                options=["open", "fixed", "ignore"],
                index=["open","fixed","ignore"].index(rec["status"]),
                key=f"select_{i}"
            )
            rec["status"] = new_status
        with col4:
            st.write("")

        updated_records.append(rec)

    st.session_state["records_state"] = updated_records

    if st.button("Save Changes"):
        save_state_to_json()
        st.success("ステータスを保存しました。")

st.subheader("Run 404 Check Manually")
if st.button("Run 404 Check Now"):
    st.info("Checking... This may take a while.")
    run_check_404()
    st.session_state["records_state"] = load_not_found_data()["data"]
    st.success("再チェック完了しました。最新結果を反映。")
