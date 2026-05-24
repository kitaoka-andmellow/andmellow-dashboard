# mellow 在庫管理

Amazon・楽天で販売する商品を、mellow側の単品在庫を基準に管理するアプリです。

## 画面

- ホーム
- 単品
- 販売SKU
- 注文
- AI

## ローカル起動

```bash
npm install
npm run dev
```

http://localhost:3000 を開きます。

## 本番化の想定

- Frontend / Backend: Next.js on Cloud Run
- Database: Cloud SQL PostgreSQL
- Images: Cloud Storage
- Jobs: Cloud Scheduler + Cloud Run Jobs
- AI: OpenAI Responses API
- Amazon: Selling Partner API
- Rakuten: RMS API
