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
# （本例ではリポジトリ内に data/ フォルダを作成し保存）
NOT_FOUND_JSON_PATH = "data/not_found_links.json"

def fetch_sitemap(url):
    """
    指定したサイトマップURLを取得し、XMLのルート要素を返す。
    失敗時はNone。
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
    サイトマップの <sitemap><loc>...</loc></sitemap> を全て取得
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
    サブサイトマップの <url><loc>...</loc></url> を全て取得
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
    メインサイトマップ -> サブサイトマップ -> 各URL の階層を再帰的にたどり、
    全てのページURLを取得して返す。
    """
    all_urls = []
    root = fetch_sitemap(url)
    if root is None:
        return all_urls

    subs = extract_sitemap_urls(root)
    if subs:
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
        all_urls.extend(extract_page_urls(root))

    # 重複排除
    all_urls = list(set(all_urls))
    return all_urls

def find_all_links_in_page(page_url):
    """
    指定ページのHTMLを取得し、<a href="..."> の全リンクを返す（ドメイン制限なし）。
    """
    links = []
    try:
        resp = requests.get(page_url, timeout=10)
        if resp.status_code != 200:
            # ページ自体が200でなければリンクは解析しない
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
    1) ページ自体が404なら [(page_url, "SELF")] を返す。
    2) ページが200の場合のみ、ページ内リンクをHEADリクエストし、
       404なら [(リンク先, page_url)] にまとめて返す。
    """
    not_found_list = []

    # まずページ自体のステータスを確認
    try:
        r_page = requests.head(page_url, timeout=10)
        if r_page.status_code == 404:
            # 記事ページ自体が404
            not_found_list.append((page_url, "SELF"))
            return not_found_list  # そもそも本文は取得できないのでリンクチェック終了
    except Exception as e:
        print(f"[Warning] check_page_and_links_404() -> HEAD {page_url} error: {e}")
        # 通信エラー等の場合はリンクチェックせずスキップ
        return not_found_list

    # ページが200の場合のみ、内部/外部リンクを全て拾って404確認
    links = find_all_links_in_page(page_url)
    for link in links:
        try:
            r_link = requests.head(link, timeout=10)
            if r_link.status_code == 404:
                not_found_list.append((link, page_url))
        except Exception as e:
            print(f"[Warning] check_page_and_links_404: link={link}, error={e}")

    return not_found_list

def load_not_found_data():
    """
    既存の not_found_links.json を読み込み、辞書にして返す。
    無ければ空のリストを返す。
    """
    if os.path.exists(NOT_FOUND_JSON_PATH):
        with open(NOT_FOUND_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"data": []}

def save_not_found_data(data):
    """
    not_found_links.json に保存。
    """
    os.makedirs(os.path.dirname(NOT_FOUND_JSON_PATH), exist_ok=True)
    with open(NOT_FOUND_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_not_found_list(new_404_list):
    """
    既存の 404リスト と 新規に検知された 404リスト を突き合わせ、統合する。
    形式: { "data": [ {"url": ..., "parent": ..., "status": ...}, ... ] }
    """
    existing_data = load_not_found_data()
    existing_records = existing_data["data"]

    # 既存データを dict化 (key=(url, parent)) して高速アクセス
    record_dict = {
        (rec["url"], rec["parent"]): rec
        for rec in existing_records
    }

    # 新しい404レコードを登録/更新
    for (url, parent) in new_404_list:
        key = (url, parent)
        if key not in record_dict:
            record_dict[key] = {
                "url": url,
                "parent": parent,
                "status": "open",  # 新規検知時は open 状態にする
            }
        # 既存の場合、statusをそのまま残す

    # 結果を保存形式に戻す
    merged_data = {"data": list(record_dict.values())}
    save_not_found_data(merged_data)

    return merged_data

def send_teams_notification(message):
    """
    TeamsのWebhookに対してメッセージをPOSTする（MessageCard形式）。
    """
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
            print(f"[Error] Teams responded with status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[Error] Failed to send Teams notification: {e}")

def main():
    print("[Info] Starting 404 check ...")

    # 1) サイトマップから全URLを取得
    all_pages = get_all_urls_from_sitemaps(MAIN_SITEMAP_URL)
    print(f"[Info] Found {len(all_pages)} pages from sitemaps in total.")

    # 2) 「https://digi-mado.jp/article/」 で始まるものだけを対象にする
    article_pages = [url for url in all_pages if url.startswith("https://digi-mado.jp/article/")]
    print(f"[Info] Filtered down to {len(article_pages)} article pages.")

    new_404_list = []
    # 3) 各記事ページ自体の404と、記事ページ内リンクの404を検出
    for page_url in article_pages:
        _404s = check_page_and_links_404(page_url)
        if _404s:
            new_404_list.extend(_404s)

    # 4) 新規に見つかった404が無ければ通知の上で終了
    if not new_404_list:
        msg = "【404チェック結果】新規に検出された404はありません。"
        print(msg)
        send_teams_notification(msg)
        print("[Info] Done.")
        return

    # 5) 既存の 404データとマージして保存
    merged_data = update_not_found_list(new_404_list)

    # 6) 新しく検出された404のリストを Teams に通知
    lines = []
    for (url, parent) in new_404_list:
        lines.append(f"- {url} (from: {parent})")
    msg = "【404チェック結果】\n以下のリンクが新たに404と判定されました:\n" + "\n".join(lines)

    print("[Info] Sending Teams notification...")
    send_teams_notification(msg)
    print("[Info] Done.")

if __name__ == "__main__":
    main()
