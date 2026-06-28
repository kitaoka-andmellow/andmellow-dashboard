# Amazon Review Request Batch

Amazon Selling Partner APIを使って、対象注文に対してAmazon公式のレビューリクエストを送信する定期実行バッチです。

## 役割

- Orders APIで対象期間の出荷済み注文を取得
- Solicitations APIで、各注文にレビュー依頼アクションが残っているか確認
- 利用可能な注文にだけ `productReviewAndSellerFeedback` を送信
- 注文IDや送信済み履歴はリポジトリに保存しない

public repoでも安全に置けるよう、認証情報・注文ID・顧客情報はコミットしない構成です。

## GitHub Secrets

Repository Settings → Secrets and variables → Actions → Repository secrets に以下を登録してください。

| Secret | 必須 | 内容 |
|---|---:|---|
| `LWA_CLIENT_ID` | 必須 | Amazon SP-APIアプリのLWA Client ID |
| `LWA_CLIENT_SECRET` | 必須 | Amazon SP-APIアプリのLWA Client Secret |
| `LWA_REFRESH_TOKEN` | 必須 | 自己認可で取得したRefresh Token |
| `AMAZON_MARKETPLACE_ID` | 必須 | 日本Amazonは通常 `A1VC38T7YXB528` |
| `AMAZON_SP_API_AWS_ACCESS_KEY_ID` | 必須 | SP-API署名用のAWS Access Key ID |
| `AMAZON_SP_API_AWS_SECRET_ACCESS_KEY` | 必須 | SP-API署名用のAWS Secret Access Key |
| `AMAZON_SP_API_ROLE_ARN` | 任意 | IAM RoleでSP-API接続する場合に設定 |
| `AMAZON_SP_API_AWS_SESSION_TOKEN` | 任意 | 一時クレデンシャルを直接使う場合に設定 |

## GitHub Variables

Repository Settings → Secrets and variables → Actions → Variables に以下を登録できます。

| Variable | 初期値 | 内容 |
|---|---:|---|
| `SP_API_REGION` | `FE` | 日本AmazonはFar Eastなので `FE` |
| `ORDER_LOOKBACK_DAYS` | `30` | 何日前までの注文を見るか |
| `ORDER_MIN_AGE_DAYS` | `5` | 何日以上前の注文を対象にするか |
| `MAX_REQUESTS_PER_RUN` | `200` | 1回の実行で処理する最大件数 |
| `AMAZON_REVIEW_REQUEST_DRY_RUN` | `true` | `true`なら送信せず対象確認のみ。送信開始時は`false`に変更 |

## 実行方法

GitHub Actions → Amazon Review Request Batch → Run workflow から手動実行できます。

最初は必ず `dry_run=true` で実行し、対象件数とログを確認してください。
問題なければ `dry_run=false` で手動実行し、その後 `AMAZON_REVIEW_REQUEST_DRY_RUN=false` を設定すると、毎日03:10 JSTに自動送信されます。

## ローカル実行

```bash
cd scripts/amazon_review_request
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python request_review_batch.py
```

必要な環境変数はGitHub Secretsと同じです。

## 注意

- Amazon側でレビューリクエスト可能な注文のみ送信します。
- `DRY_RUN=true` の場合は送信しません。
- `SKIP_IF_MISSING_SECRETS=true` のため、Secrets未設定の状態ではスケジュール実行されても失敗せずスキップします。
- API制限を避けるため、注文ごとに約1.2秒待機します。
