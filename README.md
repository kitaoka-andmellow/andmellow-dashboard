# ECanalytics

Amazon と楽天市場の CSV を読み込み、売上推移と商品別分析を可視化するダッシュボードです。ローカル実行と Cloud Run デプロイの両方に対応しています。

## できること

- Amazon / 楽天の売上を横並びで確認
- 商品ごとの売上、注文数、販売数量の一覧表示
- 商品別のサイズ分布、色・SKU項目分布の可視化
- Amazon 取引CSVから商品別トランザクションとセット購入率を表示
- 楽天 店舗データから日次売上推移を表示
- 取り込めたファイルと、空データ・不足データを画面上で明示

## 現在の入力元

- `/Users/kitaokamasaki/Downloads/ECanalytics/amzon-csv`
- `/Users/kitaokamasaki/Downloads/ECanalytics/rakuten-csv`

ファイル名は完全一致でなくても、キーワードで自動判定します。

## 起動方法

```bash
pip install -r requirements.txt
python3 dashboard_server.py
```

起動後、ブラウザで [http://127.0.0.1:8000](http://127.0.0.1:8000) を開いてください。

ローカル公開したい場合は以下です。

```bash
HOST=0.0.0.0 PORT=8000 python3 dashboard_server.py
```

## Google 認証

`@andmellow.jp` の Google アカウントだけに制限し、ログインセッションは 2 時間で失効します。

必要な環境変数:

```bash
AUTH_REQUIRED=1
ALLOWED_EMAIL_DOMAIN=andmellow.jp
GOOGLE_CLIENT_ID=<google-oauth-client-id>
SESSION_SECRET=<十分に長いランダム文字列>
SESSION_TTL_SECONDS=7200
```

ローカル実行例:

```bash
GOOGLE_CLIENT_ID=<google-oauth-client-id> \
SESSION_SECRET=<random-secret> \
AUTH_REQUIRED=1 \
ALLOWED_EMAIL_DOMAIN=andmellow.jp \
SESSION_TTL_SECONDS=7200 \
python3 dashboard_server.py
```

## Cloud Run

このリポジトリには Cloud Run 用の `Dockerfile`、`cloudrun.service.yaml`、`deploy_cloud_run.sh` を含めています。

最短でデプロイする場合:

```bash
./deploy_cloud_run.sh <gcp-project-id> <region> [service-name]
```

手動で行う場合:

```bash
gcloud run deploy ecanalytics \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars HOST=0.0.0.0,DATA_ROOT=/app
```

認証を有効にした Cloud Run デプロイ例:

```bash
gcloud run deploy ecanalytics \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --port 8080 \
  --set-env-vars HOST=0.0.0.0,DATA_ROOT=/app,AUTH_REQUIRED=1,ALLOWED_EMAIL_DOMAIN=andmellow.jp,GOOGLE_CLIENT_ID=<google-oauth-client-id>,SESSION_TTL_SECONDS=7200 \
  --set-secrets SESSION_SECRET=<secret-name>:latest
```

先に Secret Manager へシークレットを作っておくと安全です。

Cloud Run 上のヘルスチェックURL:

```text
/healthz
```

`cloudrun.service.yaml` を使う場合は、`REGION` / `PROJECT_ID` / `REPOSITORY` を置き換えてから適用してください。

```bash
gcloud run services replace cloudrun.service.yaml --region <region>
```

## テスト

```bash
python3 -m unittest discover -s tests
```

## いまの制約

- Cloud Run にそのまま載せた場合、CSV はコンテナイメージに含まれたものを読みます。新しい CSV を反映するには再デプロイが必要です。
- 将来的に「Google Drive に CSV を置いたら自動反映」にしたい場合は、Google Drive API か Cloud Storage を取り込み元に追加する必要があります。
- Google 認証は Google Identity Services の `id_token` をサーバー側で検証しています。`GOOGLE_CLIENT_ID` 未設定時はログインできません。
- Amazon の広告レポートは商品別費用ではないため、商品単位の広告費率はまだ出していません。
- 現在の楽天 CSV は SKU 別の期間集計なので、商品別の日次推移とセット購入率は未算出です。
- 楽天の広告費率は `運用型ポイント変倍経由ポイント付与料` 列に値がある場合のみ出します。

## 次にやると良い拡張

将来的にリアルタイム監視へ広げるなら、次の順序が実装しやすいです。

1. Amazon SP-API / 楽天 RMS API 用の取得アダプタを追加する
2. CSV 読み込みと API 取得結果を同じ正規化レイヤーに流す
3. 定期取得ジョブを追加して、時系列スナップショットを保存する
4. 粗利、広告ROAS、在庫回転などの指標を追加する
