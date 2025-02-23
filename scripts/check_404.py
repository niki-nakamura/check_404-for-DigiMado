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

# テスト用: 404を5件見つけたら打ち切る
MAX_TEST_404 = 5

def fetch_sitemap(url):
    """
    サイトマップを取得してXMLルートを返す
    """
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return ET.fromstring(r.text)
        else:
            print(f"[Error] fetch_sitemap: {url} -> HTTP {r.status_code}")
    except Exception as e:
        print(f"[Error] fetch_sitemap: {url} -> {e}")
    return None

def extract_sitemap_urls(sitemap_root):
    """
    サイトマップ配下の <sitemap><loc>...</loc></sitemap> を全て取得
    """
    urls = []
    if sitemap_root is None:
        return urls
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    for sitemap in sitemap_root.findall('ns:sitemap', ns):
        loc = sitemap.find('ns:loc', ns)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls

def extract_page_urls(sitemap_root):
    """
    サイトマップ配下の <url><loc>...</loc></url> を全て取得
    """
    urls = []
    if sitemap_root is None:
        return urls
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    for url_elem in sitemap_root.findall('ns:url', ns):
        loc = url_elem.find('ns:loc', ns)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls

def get_all_urls_from_sitemaps(url):
    """
    メインサイトマップ -> サブサイトマップ -> 各URL を再帰的に辿り、全URLを収集
    """
    all_urls = []
    root = fetch_sitemap(url)
    if root is None:
        return all_urls

    subs = extract_sitemap_urls(root)
    if subs:
        # サブサイトマップあり
        for sub in subs:
            sub_root = fetch_sitemap(sub)
            deeper_subs = extract_sitemap_urls(sub_root)
            if deeper_subs:
                for deeper_sub in deeper_subs:
                    deeper_root = fetch_sitemap(deeper_sub)
                    all_urls.extend(extract_page_urls(deeper_root))
            else:
                all_urls.extend(extract_page_urls(sub_root))
    else:
        # 直接URLが列挙されている
        all_urls.extend(extract_page_urls(root))

    all_urls = list(set(all_urls))  # 重複排除
    return all_urls

def find_all_links_in_page(page_url):
    """
    指定ページ(HTTP 200想定)のHTMLを取得し、全ての <a href="..."> を抽出して返す
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
    1) ページ自体が404の場合 -> [(page_url, "SELF")]
    2) 200の場合 -> ページ内リンクをHEADリクエスト、404なら (リンク先, page_url) を追加
    """
    not_found_list = []
    # ページ自体のステータスをHEADでチェック
    try:
        r = requests.head(page_url, timeout=10)
        if r.status_code == 404:
            not_found_list.append((page_url, "SELF"))
            return not_found_list
    except Exception as e:
        print(f"[Warning] check_page_and_links_404 HEAD {page_url}: {e}")
        return not_found_list

    # ページが有効なら、全リンクをチェック
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
    if os.path.exists(NOT_FOUND_JSON_PATH):
        with open(NOT_FOUND_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"data": []}

def save_not_found_data(data):
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
    print("[Info] Starting 404 check (test mode: up to 5 new 404s)...")

    all_pages = get_all_urls_from_sitemaps(MAIN_SITEMAP_URL)
    # 「/article/」のみ対象
    article_pages = [u for u in all_pages if u.startswith("https://digi-mado.jp/article/")]
    print(f"[Info] Filtered down to {len(article_pages)} /article/ pages")

    new_404_list = []
    for page_url in article_pages:
        # ページ自体 + ページ内リンクの404をチェック
        found_404s = check_page_and_links_404(page_url)
        new_404_list.extend(found_404s)

        # テスト用: 404を5件検出したら打ち切り
        if len(new_404_list) >= MAX_TEST_404:
            print(f"[Info] Reached {MAX_TEST_404} 404s. Stopping further checks.")
            break

    if not new_404_list:
        msg = "【404チェック結果】新規404はありません。"
        print(msg)
        send_teams_notification(msg)
        return

    # JSONに統合
    merged_data = update_not_found_list(new_404_list)

    # Teams通知用メッセージ作成
    lines = []
    for (url, parent) in new_404_list:
        lines.append(f"- {url} (from: {parent})")
    msg = "【404チェック結果 (TEST MODE)】\n以下のURLが新たに404でした:\n" + "\n".join(lines)

    print("[Info] Sending Teams notification...")
    send_teams_notification(msg)
    print("[Info] Done.")

if __name__ == "__main__":
    main()
