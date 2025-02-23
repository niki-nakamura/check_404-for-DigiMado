

## 1. リポジトリ構成例

```
check_404-for-DigiMado/
├─ .github/
│   └─ workflows/
│       └─ check_404.yml
├─ scripts/
│   └─ check_404.py
├─ streamlit_app.py
├─ requirements.txt
└─ README.md
```

- **.github/workflows/check_404.yml**  
  - GitHub Actions のワークフロー定義ファイルです。手動トリガー時に `scripts/check_404.py` を実行し、404を検出したらTeams通知まで行います。

- **scripts/check_404.py**  
  - 実際に404チェックを行うPythonスクリプトです。サイトマップの階層を再帰的に取得し、ステータスコードを判定して404だけ抽出。Teams Webhook への通知機能を含みます。

- **streamlit_app.py**  
  - Streamlit での可視化・監視用アプリの例です。ボタンひとつで404チェックを走らせ、結果を画面上に出力、同時にTeams通知も行う流れを想定しています。

- **requirements.txt**  
  - `requests`, `streamlit` など、Pythonライブラリの依存関係をまとめます。

- **README.md**  
  - セットアップ手順、GitHub Actionsの使い方、Streamlitの起動方法などを簡潔にまとめます。

---

## 2. GitHub Actions ワークフロー（`check_404.yml`）

```yaml
name: Check 404

# 手動トリガーのみで実行
on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Check out the repo
        uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run 404 check script
        # secrets.TEAMS_WEBHOOK_URL は GitHub の「Settings > Secrets and variables > Actions」で登録してください
        env:
          TEAMS_WEBHOOK_URL: ${{ secrets.TEAMS_WEBHOOK_URL }}
        run: |
          python scripts/check_404.py
```

- **ポイント**
  - `on: workflow_dispatch` なので、**Actions > Workflows > "Check 404"** を選び、手動で「Run workflow」するたびに404チェックが走り、結果がTeams通知されます。
  - `TEAMS_WEBHOOK_URL` は**GitHubリポジトリのSecrets**に設定しておきます。

---

## 3. 404チェックスクリプト（`scripts/check_404.py`）

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import xml.etree.ElementTree as ET
import os

# Microsoft TeamsのWebhook URL（GitHub Secretsや環境変数にて設定）
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")

# 404チェック対象サイトを https://digi-mado.jp/ に変更
MAIN_SITEMAP_URL = "https://digi-mado.jp/sitemap.xml"

def fetch_sitemap(url):
    """
    指定したサイトマップURLを取得し、XMLのルート要素を返す。
    失敗時はNone。
    """
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            return root
    except Exception as e:
        print(f"[Error] Failed to fetch sitemap: {url} \n {e}")
    return None

def extract_sitemap_urls(sitemap_root):
    """
    ルート要素から <loc> を持つサブサイトマップURLをリストで返す。
    たとえば <sitemap><loc>～</loc></sitemap> のURLが対象。
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
    サブサイトマップ（URLリストが直接含まれるもの）から <url><loc>～</loc></url> のURLを取得。
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
    すべてのWebページURLを集めて返す。
    """
    all_urls = []
    root = fetch_sitemap(url)
    if root is None:
        return all_urls

    subs = extract_sitemap_urls(root)
    if subs:
        # サブサイトマップがある場合
        for sub in subs:
            sub_root = fetch_sitemap(sub)
            deeper_subs = extract_sitemap_urls(sub_root)
            if deeper_subs:
                # さらに深いサイトマップがある場合
                for deeper_sub in deeper_subs:
                    deeper_root = fetch_sitemap(deeper_sub)
                    all_urls.extend(extract_page_urls(deeper_root))
            else:
                all_urls.extend(extract_page_urls(sub_root))
    else:
        # URLリストを直接持つサイトマップ
        all_urls.extend(extract_page_urls(root))

    return all_urls

def check_404_urls(url_list):
    """
    GETリクエストし、レスポンスが404のURLをリストで返す。
    """
    not_found = []
    for u in url_list:
        try:
            resp = requests.get(u, timeout=10)
            if resp.status_code == 404:
                not_found.append(u)
        except Exception as e:
            print(f"[Warning] Request error for {u}: {e}")
    return not_found

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

    # 1) サイトマップから全URLを抽出
    all_urls = get_all_urls_from_sitemaps(MAIN_SITEMAP_URL)
    print(f"[Info] Found {len(all_urls)} URLs in sitemap(s).")

    # 2) 404のURLをチェック
    not_found_urls = check_404_urls(all_urls)

    # 3) Teams通知用メッセージを作成
    if not not_found_urls:
        message = "【404チェック結果】\n404は検出されませんでした。"
    else:
        message = "【404チェック結果】\n以下のURLが404でした:\n" + "\n".join(not_found_urls)

    # 4) Teamsへ通知
    print("[Info] Sending Teams notification...")
    send_teams_notification(message)
    print("[Info] Done.")

if __name__ == "__main__":
    main()
```

---

## 4. Streamlitアプリ例（`streamlit_app.py`）

下記は**手動での404チェック＆結果表示**を簡易化する例です。  
（実運用では、定期的に実行するGitHub Actionsとあわせて、必要に応じて手元で追加確認したい場合などに活用できます。）

```python
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
```

- **ポイント**
  - `Run 404 Check` ボタンを押すとスクリプト内の404判定ロジックが実行され、その結果をStreamlit画面上に表示します。
  - 同時にTeams通知も送信されます。
  - `.env` や OS の環境変数として `TEAMS_WEBHOOK_URL` を設定しておくことで、ローカルでも簡易的にTeams通知の動作確認ができます（Herokuなどにデプロイする場合も同様）。

---

## 5. requirements.txt 例

```txt
requests==2.28.1
streamlit==1.18.1
```

必要に応じてバージョンは調整してください。

---

## 6. README.md 例

```md
# check_404-for-DigiMado

DigiMadoサイトの404検出ツールです。  
GitHub Actionsを使って手動で404チェックを実行し、Teams通知を行います。  
また、Streamlitアプリを使ってローカルまたは任意のサーバでGUI上からチェックや結果参照ができます。

## セットアップ

1. リポジトリをクローンする
2. Python 3.x をインストール
3. 下記で依存パッケージをインストール

```bash
pip install -r requirements.txt
```

4. `.env` または OS の環境変数で `TEAMS_WEBHOOK_URL` を設定（任意）
   - ローカルでStreamlitアプリを使用する場合に必要  
   - GitHub Actionsで使用する場合は、リポジトリの Secrets ( `Settings > Secrets > Actions` ) に `TEAMS_WEBHOOK_URL` を設定してください

## 使い方

### 1) GitHub Actionsで手動実行

- GitHubリポジトリの「Actions」タブを開く
- 「Check 404」ワークフローを選び、「Run workflow」で実行
- 実行完了時に、`scripts/check_404.py` が走り、404 URLがあればTeamsに通知されます

### 2) Streamlitでローカル実行

```bash
streamlit run streamlit_app.py
```

- ブラウザで表示されるDashboard上で「Run 404 Check」ボタンを押すと検査が走ります
- 結果が画面に表示され、同時にTeams通知も送信（Webhook設定があれば）されます

## ファイル構成

- `.github/workflows/check_404.yml`
  - GitHub Actions用のワークフロー
- `scripts/check_404.py`
  - 404チェックを行うスクリプト（サイトマップ取得～Teams通知まで）
- `streamlit_app.py`
  - StreamlitでGUI操作＆Teams通知を行う簡易ダッシュボード
- `requirements.txt`
  - Pythonパッケージの依存関係
- `README.md`
  - 本ファイル

```

---

## 7. ツール実行フロー解説

1. **GitHub Actionsによる実行**  
   - リポジトリのActionsタブから手動実行  
   - `.github/workflows/check_404.yml` が起動し、`scripts/check_404.py` を実行  
   - サイトマップ( `https://digi-mado.jp/sitemap.xml` )を再帰的に辿って全URLを取得  
   - 各URLに対してGETリクエストを送り、404かどうかを判定  
   - 404があればURLリストをTeamsへ送信し、なければ「404なし」のメッセージをTeams送信  
   - （終わり）

2. **Streamlitアプリによる手動チェック (ローカル/サーバ上)**  
   - `streamlit_app.py` を `streamlit run streamlit_app.py` で起動  
   - ブラウザ上にアクセスし、「Run 404 Check」ボタンを押下  
   - 同じく `check_404.py` のロジックが呼ばれ、結果が画面に一覧表示  
   - 同時にTeams通知（環境変数 `TEAMS_WEBHOOK_URL` があれば）  
   - （終わり）

