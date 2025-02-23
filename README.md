
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

以上の流れで、**Google Sheetsを使わず**に404を監視し、Teamsへリアルタイムに通知するツールとして機能します。必要に応じて改良や運用スケジュールの設定を行ってください。これで **「404感知ツールをStreamlit + Teams通知で管理」** する構成が完成です。
