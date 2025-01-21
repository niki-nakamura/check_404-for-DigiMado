以下の手順では、Slack用のアラートボットを「Microsoft Teams で実行する」ために必要な作業を、誰でも再現できるように丁寧に解説します。  
（※ 前提：Python での基本的な開発環境があり、Teams 側でも権限を持って操作できる状態を想定しています）

---

## 1. Microsoft Teams への「Incoming Webhook」アプリの追加

Teams でメッセージを受け取る場合、**Incoming Webhook（着信Webhook）** を利用するのが簡単です。Slack の Incoming Webhook と同様の機能を持ち、POST したメッセージを特定のチャンネルに表示することが可能です。

1. **Teams を開く**
   - ブラウザ版でもデスクトップアプリ版でもOKです。

2. **チームまたはチャネルを選択**
   - Microsoft Teams の左側のバーから「チーム」を選択し、メッセージを通知したい特定のチャネルを開きます。

3. **チャンネルの「…」メニュー（その他のオプション）から「コネクタ」を選択**
   - もしくは「チーム名の右側にある `…`」→「コネクタ」を選択します。

4. **「Incoming Webhook」を追加**
   - コネクタの一覧から「Incoming Webhook」を探し、「追加」ボタンをクリックします。
   - もしすぐに見つからない場合は検索ボックスで `Incoming Webhook` を検索してください。

5. **Webhook の名前とアイコンを設定**
   - Webhook 名をわかりやすいもの（例: `Google Search Status Bot`）に変更可能です。
   - 任意でアイコン画像も設定できます。

6. **Webhook URL をコピー**
   - Webhook が作成されると、その「Webhook URL」が表示されますのでコピーします。
   - これを後ほど Python スクリプトの環境変数や設定ファイルに設定します。

---

## 2. 環境変数を設定する

Slack のときと同様、セキュリティのために「Webhook URL」は環境変数として扱うのがオススメです。  
例として `TEAMS_WEBHOOK_URL` という名前で設定すると良いでしょう。

### Windows の場合（PowerShell の例）

```powershell
$Env:TEAMS_WEBHOOK_URL = "＜コピーした Webhook URL＞"
```

### macOS / Linux の場合（bash の例）

```bash
export TEAMS_WEBHOOK_URL="＜コピーした Webhook URL＞"
```

なお、実際にサーバーやDocker上で運用する場合は、その環境の変数管理方法（.envファイルやCI/CDシステムでの秘匿情報管理など）に応じて設定してください。

---

## 3. Python コードの変更

### 3-1. Slack 用から Teams 用に変更

Slack の場合は `"text"` キーにメッセージを入れるだけでしたが、Teams の Incoming Webhook では**MessageCard フォーマット**を利用します。最低限、以下のような JSON で送信すると、Teams でカード形式のメッセージが表示されます。

```python
def post_to_teams(webhook_url, summary, link, date_, duration):
    # Teams カード用のペイロードを作成
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": "Ranking Info",
        "themeColor": "0078D7",  # 好みのカラーコード (例: Teamsのブランドカラー)
        "title": "Ranking 最新情報",
        "text": (
            f"**Summary:** {summary}  \n"    # MarkDown 風に改行するには "  \n" などを使います
            f"**Link:** {link}  \n"
            f"**Date:** {date_}  \n"
            f"**Duration:** {duration}"
        )
    }

    response = requests.post(webhook_url, json=payload)
    response.raise_for_status()
```

上記のように、Teams では Markdown 形式での装飾が可能です。  
- `**Summary:**` のように `** 〜 **` で太字が使えます。  
- 単純に改行する場合は `  \n` （半角スペース2つ＋`\n`）を使うなど、少しだけ書式に注意しましょう。

### 3-2. メインコードの修正例

もとのSlack用のコードを参考に、Teams 用の関数を呼び出す形に書き換えると以下のようになります。
（※ 変数名やコメントなどは自由に変えてOKです）

```python
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse

def get_latest_ranking_info(url):
    # ダッシュボードを取得
    response = requests.get(url)
    response.raise_for_status()

    # パース
    soup = BeautifulSoup(response.text, "html.parser")

    # 「Ranking」と書かれた要素を取得
    ranking_span = soup.find("span", class_="nAlKgGlv8Vo__product-name", string="Ranking")
    if not ranking_span:
        return None

    # 次に出てくるテーブルを取得
    ranking_table = ranking_span.find_next("table", class_="ise88CpWulY__psd-table")
    if not ranking_table:
        return None

    # tbody -> 最初の <tr>
    first_row = ranking_table.find("tbody").find("tr")
    if not first_row:
        return None

    # Summary (タイトル)
    summary_td = first_row.find("td", class_="ise88CpWulY__summary")
    summary_text = summary_td.get_text(strip=True) if summary_td else None
    link_tag = summary_td.find("a") if summary_td else None
    summary_link = urllib.parse.urljoin(url, link_tag.get("href")) if link_tag else None

    # Date
    date_td = first_row.find("td", class_="ise88CpWulY__date")
    date_text = date_td.get_text(strip=True) if date_td else None

    # Duration
    duration_td = first_row.find("td", class_="ise88CpWulY__duration")
    duration_span = duration_td.find("span", class_="ise88CpWulY__duration-text") if duration_td else None
    duration_text = duration_span.get_text(strip=True) if duration_span else None

    return summary_text, summary_link, date_text, duration_text

def post_to_teams(webhook_url, summary, link, date_, duration):
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": "Ranking Info",
        "themeColor": "0078D7",
        "title": "Ranking 最新情報",
        "text": (
            f"**Summary:** {summary}  \n"
            f"**Link:** {link}  \n"
            f"**Date:** {date_}  \n"
            f"**Duration:** {duration}"
        )
    }

    response = requests.post(webhook_url, json=payload)
    response.raise_for_status()

def main():
    URL = "https://status.search.google.com/summary"
    info = get_latest_ranking_info(URL)

    if not info:
        print("Ranking 情報が取得できませんでした。")
        return

    summary, link, date_, duration = info

    # 環境変数から Teams の Webhook URL を取得
    teams_webhook_url = os.environ.get("TEAMS_WEBHOOK_URL")
    if not teams_webhook_url:
        print("TEAMS_WEBHOOK_URL が設定されていません。")
        return

    # Teams に投稿
    post_to_teams(teams_webhook_url, summary, link, date_, duration)
    print("Teams に投稿しました。")

if __name__ == "__main__":
    main()
```

---

## 4. 実行・動作確認

1. **Python スクリプトを実行**  
   ```bash
   python main.py
   ```
   - もし `TEAMS_WEBHOOK_URL` が設定されていれば、Teams にカード形式のメッセージが投稿されます。

2. **Teams 側でメッセージを確認**  
   - 指定したチャンネルに、上記フォーマットのメッセージカードが届いているはずです。

---

## 5. Teams に「アプリ」として表示する運用イメージ

Teams での「アプリ追加」は、実際には「Incoming Webhook コネクタを追加する」作業に相当します。もしもっと高度な「Teams アプリ」という形で配信したい場合は、Microsoft 365 開発者向けのドキュメントを参考にして「Teams アプリ（Manifests や Azure Bot サービス）」を利用する方法もあります。ただし単純な“アナウンス用”の通知であれば、**Incoming Webhook** が手軽で管理コストも低いのでおすすめです。

---

## 6. よくある質問・つまずきポイント

1. **メッセージが反映されない**
   - 環境変数が正しく設定されているか？
   - Webhook URL をコピペミスしていないか？
   - チャンネルが「プライベート チャンネル」など特殊な設定になっていないか？

2. **MessageCard でMarkdownがうまく改行されない**
   - Teams によっては改行表現が複数あるので `  \n` がうまく効かない場合があります。  
   - その際はテキストを単純に `\n` だけで区切ってみるなど試してください。

3. **会社や組織のポリシーでWebhookが制限されている**
   - 組織によっては外部連携が制限されている場合があるため、管理者に確認してから設定してください。

---

## まとめ

- Slack のときと同様の考え方で、**Teams の Incoming Webhook** を使ってメッセージを通知できます。  
- **MessageCard フォーマット**（JSON）を使うことで、Teams のチャネルにカード形式で投稿が可能です。  
- 環境変数として Webhook URL を設定し、Python で `requests.post` すればOKです。  

このようにシンプルな改修だけで、Slack のアナウンス ボットを Microsoft Teams に置き換えることができます。  
ぜひ試してみてください。  
