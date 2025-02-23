#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import json
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# Microsoft TeamsのWebhook URL（GitHub Secretsやenvなどで設定）
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")

# DigiMadoのサイトURL
BASE_URL = "https://digi-mado.jp"
MAIN_SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

# 404リストを蓄積するJSONファイルのパス
NOT_FOUND_JSON_PATH = "data/not_found_links.json"


def fetch_sitemap(url):
    ...
    # （以前と同じ）

def extract_sitemap_urls(sitemap_root):
    ...
    # （以前と同じ）

def extract_page_urls(sitemap_root):
    ...
    # （以前と同じ）

def get_all_urls_from_sitemaps(url):
    ...
    # （以前と同じ）

def find_all_links_in_page(page_url):
    """
    指定ページのHTMLを取得し、<a href="..."> の全リンクを返す（ドメイン外含む）。
    """
    links = []
    try:
        resp = requests.get(page_url, timeout=10)
        if resp.status_code != 200:
            return links
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            full_url = urljoin(page_url, a["href"])
            links.append(full_url)
    except Exception as e:
        print(f"[Warning] find_all_links_in_page({page_url}): {e}")
    return links

def check_page_and_links_404(page_url):
    """
    1) ページ自体が404なら [(page_url, "SELF")] を返す
    2) 200の場合のみ、中の全リンクにHEADリクエストし404なら (リンクURL, page_url)
    """
    not_found_list = []
    # ページ自体をHEADでチェック
    try:
        r = requests.head(page_url, timeout=10)
        if r.status_code == 404:
            not_found_list.append((page_url, "SELF"))
            return not_found_list
    except Exception as e:
        print(f"[Warning] check_page_and_links_404() HEAD {page_url}: {e}")
        return not_found_list

    # ここまで来たら記事ページ自体は200なので、中のリンクを全チェック
    links = find_all_links_in_page(page_url)
    for link in links:
        try:
            r_link = requests.head(link, timeout=10)
            if r_link.status_code == 404:
                not_found_list.append((link, page_url))
        except Exception as e:
            print(f"[Warning] check_page_and_links_404 HEAD {link}: {e}")

    return not_found_list

def load_not_found_data():
    # JSON読み込み
    if os.path.exists(NOT_FOUND_JSON_PATH):
        with open(NOT_FOUND_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"data": []}

def save_not_found_data(data):
    # JSON保存
    os.makedirs(os.path.dirname(NOT_FOUND_JSON_PATH), exist_ok=True)
    with open(NOT_FOUND_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_not_found_list(new_404_list):
    existing_data = load_not_found_data()
    existing_records = existing_data["data"]
    record_dict = {(rec["url"], rec["parent"]): rec for rec in existing_records}

    for (url, parent) in new_404_list:
        key = (url, parent)
        if key not in record_dict:
            record_dict[key] = {
                "url": url,
                "parent": parent,
                "status": "open",
            }

    merged_data = {"data": list(record_dict.values())}
    save_not_found_data(merged_data)
    return merged_data

def send_teams_notification(message):
    if not TEAMS_WEBHOOK_URL:
        print("[Error] TEAMS_WEBHOOK_URL is not set.")
        return
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": "404チェック結果",
        "text": message
    }
    try:
        r = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"[Error] Teams responded with {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[Error] Failed to send Teams notification: {e}")

def main():
    print("[Info] Starting 404 check ...")

    all_pages = get_all_urls_from_sitemaps(MAIN_SITEMAP_URL)
    # 「/article/」のみ対象
    article_pages = [u for u in all_pages if u.startswith("https://digi-mado.jp/article/")]
    print(f"[Info] Filtered down to {len(article_pages)} /article/ pages")

    new_404_list = []
    for page_url in article_pages:
        _404s = check_page_and_links_404(page_url)
        if _404s:
            new_404_list.extend(_404s)

    if not new_404_list:
        msg = "【404チェック結果】新規404はありません。"
        print(msg)
        send_teams_notification(msg)
        return

    merged_data = update_not_found_list(new_404_list)

    lines = []
    for (url, parent) in new_404_list:
        lines.append(f"- {url} (from: {parent})")
    msg = "【404チェック結果】\n以下のURLが新たに404でした:\n" + "\n".join(lines)

    print("[Info] Sending Teams notification...")
    send_teams_notification(msg)
    print("[Info] Done.")

if __name__ == "__main__":
    main()
