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
    # サブサイトマップがあるかどうか
    subs = extract_sitemap_urls(root)
    if subs:
        # サブサイトマップを辿る
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
        # サブサイトマップの無い場合は直接URLリストを取り出す
        all_urls.extend(extract_page_urls(root))

    # 重複排除
    all_urls = list(set(all_urls))
    return all_urls

def find_internal_links_in_page(page_url):
    """
    指定ページのHTMLを取得し、同ドメイン内（https://digi-mado.jp）へのリンクを全て返す。
    """
    links = []
    try:
        resp = requests.get(page_url, timeout=10)
        if resp.status_code != 200:
            # そもそもページ自体が404などの場合はリンク取得不可
            return links
        soup = BeautifulSoup(resp.text, "html.parser")
        # 全ての <a href="..."> を取得
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # 絶対URLに変換
            full_url = urljoin(page_url, href)
            # 同一ドメインのみ対象
            if same_domain(full_url, BASE_URL):
                links.append(full_url)
    except Exception as e:
        print(f"[Warning] find_internal_links_in_page({page_url}): {e}")
    return links

def same_domain(url, base):
    """
    URLが baseドメイン と同じか確認する。
    """
    parsed = urlparse(url)
    base_parsed = urlparse(base)
    return parsed.netloc == base_parsed.netloc

def check_internal_links_404(page_url):
    """
    ページ内リンクを全てチェックし、404のリンクがあれば [(リンク先, page_url)] で返す。
    """
    not_found_list = []
    links = find_internal_links_in_page(page_url)
    for link in links:
        try:
            r = requests.head(link, timeout=10)
            # GETではなくHEADを使うと多少高速化
            if r.status_code == 404:
                not_found_list.append((link, page_url))
        except Exception as e:
            print(f"[Warning] check_internal_links_404: {link} -> {e}")
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
        # ファイルが無ければ空の構造を返す
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
        else:
            # 既存の場合はstatusをそのままにする
            pass

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

    # 1) サイトマップから「全ページURL一覧」を取得
    all_pages = get_all_urls_from_sitemaps(MAIN_SITEMAP_URL)
    print(f"[Info] Found {len(all_pages)} pages from sitemap(s).")

    # 2) 各ページの内部リンクをチェックし、404の (リンク先, 検知元) を集める
    new_404_list = []
    for page_url in all_pages:
        # ページ内にあるリンクの404をチェック
        _404s = check_internal_links_404(page_url)
        if _404s:
            new_404_list.extend(_404s)

    if not new_404_list:
        # 新規に見つかった404が無い場合
        msg = "【404チェック結果】新規に検出された404はありません。"
        print(msg)
        send_teams_notification(msg)
        return

    # 3) 既存の 404データ と突き合わせ、JSONを上書き
    merged_data = update_not_found_list(new_404_list)

    # 4) Teams通知用メッセージを作成
    # 新たに検出された404だけを通知したい場合は new_404_list のみ書く、
    # 全404をまとめて通知したいなら merged_data["data"] でもOK。
    lines = []
    for url, parent in new_404_list:
        lines.append(f"- {url} (from: {parent})")
    msg = "【404チェック結果】\n以下のリンクが新たに404と判定されました:\n" + "\n".join(lines)

    # 5) Teamsへ通知
    print("[Info] Sending Teams notification...")
    send_teams_notification(msg)
    print("[Info] Done.")

if __name__ == "__main__":
    main()
