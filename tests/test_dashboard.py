from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from eanalytics import build_dashboard


class DashboardSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = build_dashboard(Path(__file__).resolve().parents[1])

    def test_dashboard_builds(self) -> None:
        self.assertGreater(len(self.payload["products"]), 0)
        self.assertGreater(len(self.payload["productDetails"]), 0)
        self.assertIn("overall", self.payload["summary"])

    def test_amazon_product_has_variant_breakdown(self) -> None:
        amazon_products = [
            self.payload["productDetails"][product["id"]]
            for product in self.payload["products"]
            if product["marketplace"] == "amazon"
        ]
        candidate = next(product for product in amazon_products if product["variants"])
        self.assertGreater(len(candidate["variants"]), 0)
        self.assertGreater(len(candidate["sizeDistribution"]), 0)
        self.assertIn("sales", candidate["summary"])

    def test_rakuten_product_has_variant_breakdown(self) -> None:
        rakuten_products = [
            self.payload["productDetails"][product["id"]]
            for product in self.payload["products"]
            if product["marketplace"] == "rakuten"
        ]
        candidate = next(product for product in rakuten_products if product["variants"])
        self.assertGreater(len(candidate["variants"]), 0)
        self.assertGreater(len(candidate["sizeDistribution"]), 0)

    def test_sources_are_registered(self) -> None:
        source_ids = {source["id"] for source in self.payload["sources"]}
        self.assertIn("amazon_transactions", source_ids)
        self.assertIn("rakuten_orders_csv", source_ids)

    def test_duplicate_files_do_not_double_count(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            base_root = temp_root / "base"
            duplicate_root = temp_root / "duplicate"
            for target in (base_root, duplicate_root):
                (target / "amzon-csv").mkdir(parents=True)
                (target / "rakuten-csv").mkdir(parents=True)

            business_src = next(path for path in (root / "amzon-csv").iterdir() if "BusinessReport" in path.name)
            rakuten_src = next(path for path in (root / "rakuten-csv").iterdir() if path.suffix == ".csv")

            shutil.copy2(business_src, base_root / "amzon-csv" / business_src.name)
            shutil.copy2(rakuten_src, base_root / "rakuten-csv" / rakuten_src.name)

            shutil.copy2(business_src, duplicate_root / "amzon-csv" / business_src.name)
            shutil.copy2(business_src, duplicate_root / "amzon-csv" / "BusinessReport-duplicate.csv")
            shutil.copy2(rakuten_src, duplicate_root / "rakuten-csv" / rakuten_src.name)
            shutil.copy2(rakuten_src, duplicate_root / "rakuten-csv" / "2025-10-duplicate.csv")

            base_payload = build_dashboard(base_root)
            duplicate_payload = build_dashboard(duplicate_root)

            base_amazon_sales = sum(
                product["sales"] for product in base_payload["products"] if product["marketplace"] == "amazon"
            )
            duplicate_amazon_sales = sum(
                product["sales"] for product in duplicate_payload["products"] if product["marketplace"] == "amazon"
            )
            base_rakuten_sales = sum(
                product["sales"] for product in base_payload["products"] if product["marketplace"] == "rakuten"
            )
            duplicate_rakuten_sales = sum(
                product["sales"] for product in duplicate_payload["products"] if product["marketplace"] == "rakuten"
            )

            self.assertEqual(duplicate_amazon_sales, base_amazon_sales)
            self.assertEqual(duplicate_rakuten_sales, base_rakuten_sales)

    def test_rakuten_variant_labels_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            content = """※この情報は店舗様および楽天市場での重要な情報となります。データの取扱には十分にご注意ください。\n\nデータ対象期間,2026/03/01 ～ 2026/03/31\nカタログID,商品管理番号,商品番号,商品名,SKU管理番号,システム連携用SKU番号,SKU項目1,SKU項目2,SKU項目3,SKU項目4,SKU項目5,SKU項目6,売上金額,売上件数,売上個数\n,30001,,テスト商品,sku-1,,ブラック(即納),M,,,,,100,1,1\n,30001,,テスト商品,sku-2,,ブラック,L,,,,,200,1,2\n,30001,,テスト商品,sku-3,,7枚【L】,M,,,,,300,1,3\n,30001,,テスト商品,sku-4,,7枚【L】デイリー,M,,,,,400,1,4\n,30001,,テスト商品,sku-5,,5枚セット【C】,M,,,,,500,1,5\n,30001,,テスト商品,sku-6,,5枚セットC,M,,,,,600,1,6\n,30001,,テスト商品,sku-7,,5枚セット【C】デイリー,M,,,,,700,1,7\n"""
            (root / "rakuten-csv" / "20260301_20260331_日次_SKU別売上データ.csv").write_text(
                content,
                encoding="utf-8",
            )

            payload = build_dashboard(root)
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "rakuten"
            )
            colors = {item["label"]: item["sales"] for item in product["colorDistribution"]}
            self.assertEqual(colors["ブラック"], 300.0)
            self.assertEqual(colors["7枚【L】デイリー"], 700.0)
            self.assertEqual(colors["5枚セット【C】デイリー"], 1800.0)
            self.assertNotIn("7枚【L】", colors)
            self.assertNotIn("5枚セット【C】", colors)
            self.assertNotIn("5枚セットC", colors)

    def test_period_filter_limits_rakuten_variant_totals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            march = """※この情報は店舗様および楽天市場での重要な情報となります。データの取扱には十分にご注意ください。\n\nデータ対象期間,2026/03/01 ～ 2026/03/31\nカタログID,商品管理番号,商品番号,商品名,SKU管理番号,システム連携用SKU番号,SKU項目1,SKU項目2,SKU項目3,SKU項目4,SKU項目5,SKU項目6,売上金額,売上件数,売上個数\n,30001,,テスト商品,sku-1,,ピンク,M,,,,,100,1,1\n"""
            april = """※この情報は店舗様および楽天市場での重要な情報となります。データの取扱には十分にご注意ください。\n\nデータ対象期間,2026/04/01 ～ 2026/04/30\nカタログID,商品管理番号,商品番号,商品名,SKU管理番号,システム連携用SKU番号,SKU項目1,SKU項目2,SKU項目3,SKU項目4,SKU項目5,SKU項目6,売上金額,売上件数,売上個数\n,30001,,テスト商品,sku-2,,ピンク,M,,,,,200,1,2\n"""
            (root / "rakuten-csv" / "20260301_20260331_日次_SKU別売上データ.csv").write_text(march, encoding="utf-8")
            (root / "rakuten-csv" / "20260401_20260430_日次_SKU別売上データ.csv").write_text(april, encoding="utf-8")

            payload = build_dashboard(root, period_start="2026-03-01", period_end="2026-03-31")
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "rakuten"
            )

            self.assertEqual(product["summary"]["sales"], 100.0)
            self.assertEqual(product["summary"]["units"], 1.0)

    def test_size_distribution_uses_size_order_not_sales_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            content = """※この情報は店舗様および楽天市場での重要な情報となります。データの取扱には十分にご注意ください。\n\nデータ対象期間,2026/03/01 ～ 2026/03/31\nカタログID,商品管理番号,商品番号,商品名,SKU管理番号,システム連携用SKU番号,SKU項目1,SKU項目2,SKU項目3,SKU項目4,SKU項目5,SKU項目6,売上金額,売上件数,売上個数\n,30001,,テスト商品,sku-1,,ピンク,XL,,,,,400,1,4\n,30001,,テスト商品,sku-2,,ピンク,S,,,,,100,1,1\n,30001,,テスト商品,sku-3,,ピンク,M,,,,,200,1,2\n,30001,,テスト商品,sku-4,,ピンク,L,,,,,300,1,3\n,30001,,テスト商品,sku-5,,ピンク,2XL,,,,,500,1,5\n,30001,,テスト商品,sku-6,,ピンク,36,,,,,600,1,6\n,30001,,テスト商品,sku-7,,ピンク,40,,,,,700,1,7\n,30001,,テスト商品,sku-8,,ピンク,38,,,,,650,1,6\n"""
            (root / "rakuten-csv" / "20260301_20260331_日次_SKU別売上データ.csv").write_text(
                content,
                encoding="utf-8",
            )

            payload = build_dashboard(root)
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "rakuten"
            )
            labels = [item["label"] for item in product["sizeDistribution"]]
            self.assertEqual(labels, ["36", "38", "40", "S", "M", "L", "XL", "2XL"])

    def test_amazon_variant_has_daily_timeline_when_transactions_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            business = """（親）ASIN,（子）ASIN,タイトル,セッション数 - 合計,注文された商品点数,ユニットセッション率,注文商品の売上額,注文品目総数\nPARENT1,CHILD1,"テスト商品 (ブラック, M)",10,1,10%,1000,2\n"""
            transactions = """日付,注文番号,商品の詳細,商品価格合計,プロモーション割引合計,Amazon手数料,合計 (JPY),トランザクションの種類,トランザクションステータス,数量\n2026/03/05,ORDER-1,"テスト商品 (ブラック, M)",1000,0,-100,900,注文に対する支払い,完了,2\n"""
            (root / "amzon-csv" / "BusinessReport-2026-03.csv").write_text(business, encoding="utf-8")
            (root / "amzon-csv" / "取引-20260301_20260331.csv").write_text(transactions, encoding="utf-8")

            payload = build_dashboard(root)
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "amazon"
            )
            variant = product["variants"][0]

            self.assertTrue(variant["timelineAvailable"])
            self.assertEqual(variant["timeline"], [{"date": "2026-03-05", "sales": 1000.0, "units": 2.0}])

    def test_amazon_period_filter_recomputes_summary_from_transaction_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            business = """（親）ASIN,（子）ASIN,タイトル,セッション数 - 合計,注文された商品点数,ユニットセッション率,注文商品の売上額,注文品目総数\nPARENT1,CHILD1,"テスト商品 (ブラック, M)",10,2,10%,3000,5\n"""
            transactions = """日付,注文番号,商品の詳細,商品価格合計,プロモーション割引合計,Amazon手数料,合計 (JPY),トランザクションの種類,トランザクションステータス,数量\n2026/03/05,ORDER-1,"テスト商品 (ブラック, M)",1000,0,-100,900,注文に対する支払い,完了,2\n2026/03/10,ORDER-2,"テスト商品 (ブラック, M)",2000,0,-200,1800,注文に対する支払い,完了,3\n"""
            (root / "amzon-csv" / "BusinessReport-2026-03.csv").write_text(business, encoding="utf-8")
            (root / "amzon-csv" / "取引-20260301_20260331.csv").write_text(transactions, encoding="utf-8")

            payload = build_dashboard(root, period_start="2026-03-05", period_end="2026-03-05")
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "amazon"
            )
            variant = product["variants"][0]

            self.assertEqual(product["summary"]["sales"], 1000.0)
            self.assertEqual(product["summary"]["units"], 2.0)
            self.assertEqual(variant["sales"], 1000.0)
            self.assertEqual(variant["units"], 2.0)
            self.assertEqual(variant["timeline"], [{"date": "2026-03-05", "sales": 1000.0, "units": 2.0}])

    def test_color_distribution_uses_name_order_not_sales_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            content = """※この情報は店舗様および楽天市場での重要な情報となります。データの取扱には十分にご注意ください。\n\nデータ対象期間,2026/03/01 ～ 2026/03/31\nカタログID,商品管理番号,商品番号,商品名,SKU管理番号,システム連携用SKU番号,SKU項目1,SKU項目2,SKU項目3,SKU項目4,SKU項目5,SKU項目6,売上金額,売上件数,売上個数\n,30001,,テスト商品,sku-1,,うすべに,M,,,,,900,1,9\n,30001,,テスト商品,sku-2,,あか,M,,,,,100,1,1\n,30001,,テスト商品,sku-3,,10,M,,,,,800,1,8\n,30001,,テスト商品,sku-4,,2,M,,,,,700,1,7\n,30001,,テスト商品,sku-5,,1,M,,,,,600,1,6\n"""
            (root / "rakuten-csv" / "20260301_20260331_日次_SKU別売上データ.csv").write_text(
                content,
                encoding="utf-8",
            )

            payload = build_dashboard(root)
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "rakuten"
            )
            labels = [item["label"] for item in product["colorDistribution"]]
            self.assertEqual(labels, ["あか", "うすべに", "1", "2", "10"])

    def test_amazon_transaction_csv_supports_daily_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            business = """（親）ASIN,（子）ASIN,タイトル,セッション数 - 合計,注文された商品点数,ユニットセッション率,注文商品の売上額,注文品目総数\nPARENT1,CHILD1,"テスト商品 (ブラック, M)",10,2,10%,3000,3\n"""
            transactions = """日付,注文番号,商品の詳細,商品価格合計,プロモーション割引合計,Amazon手数料,合計 (JPY),トランザクションの種類,トランザクションステータス,数量\n2026/03/05,ORDER-1,\"テスト商品 (ブラック, M)\",1000,0,-100,900,注文に対する支払い,完了,2\n"""
            (root / "amzon-csv" / "BusinessReport-2026-03.csv").write_text(business, encoding="utf-8")
            (root / "amzon-csv" / "取引-20260301_20260331.csv").write_text(transactions, encoding="utf-8")

            payload = build_dashboard(root, period_start="2026-03-05", period_end="2026-03-05")
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "amazon"
            )
            variant = product["variants"][0]

            self.assertEqual(product["summary"]["sales"], 1000.0)
            self.assertEqual(product["summary"]["units"], 2.0)
            self.assertTrue(variant["timelineAvailable"])
            self.assertEqual(variant["timeline"], [{"date": "2026-03-05", "sales": 1000.0, "units": 2.0}])

    def test_amazon_txt_period_filter_recomputes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            business = """（親）ASIN,（子）ASIN,タイトル,セッション数 - 合計,注文された商品点数,ユニットセッション率,注文商品の売上額,注文品目総数\nPARENT1,CHILD1,"テスト商品 (ブラック, M)",10,2,10%,3000,3\n"""
            order_report = """amazon-order-id\tmerchant-order-id\tpurchase-date\tlast-updated-date\torder-status\tfulfillment-channel\tsales-channel\torder-channel\turl\tship-service-level\tproduct-name\tsku\tasin\titem-status\tquantity\tcurrency\titem-price\titem-tax\tshipping-price\tshipping-tax\tgift-wrap-price\tgift-wrap-tax\titem-promotion-discount\tship-promotion-discount\tship-city\tship-state\tship-postal-code\tship-country\tpromotion-ids\n249-0000000-0000001\t\t2026-03-05T10:00:00+09:00\t2026-03-05T10:00:00+09:00\tShipped\tAmazon\tAmazon.co.jp\t\t\tStandard\t[&mellow] テスト商品 (JP, アルファベット, M, ブラック)\tSKU-1\tCHILD1\tShipped\t2\tJPY\t1000\t0\t0\t0\t0\t0\t0\t0\t東京都\t東京\t1000001\tJP\t\n"""
            (root / "amzon-csv" / "BusinessReport-2026-03.csv").write_text(business, encoding="utf-8")
            (root / "amzon-csv" / "orders-202603.txt").write_text(order_report, encoding="cp932")

            payload = build_dashboard(root, period_start="2026-03-05", period_end="2026-03-05")
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "amazon"
            )
            variant = product["variants"][0]

            self.assertEqual(product["summary"]["sales"], 1000.0)
            self.assertEqual(product["summary"]["units"], 2.0)
            self.assertTrue(variant["timelineAvailable"])
            self.assertEqual(variant["timeline"], [{"date": "2026-03-05", "sales": 1000.0, "units": 2.0}])

    def test_amazon_business_report_groups_renamed_titles_by_parent_asin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            business = """（親）ASIN,（子）ASIN,タイトル,セッション数 - 合計,注文された商品点数,ユニットセッション率,注文商品の売上額,注文品目総数
PARENT1,ASIN-1,\"[&mellow] 温活ショーツ 5枚セット 綿95% ハイウエスト レディース (JP, アルファベット, M, ブラック)\",10,1,10%,1000,1
PARENT1,ASIN-2,\"[&mellow] 温活ショーツ 5枚セット 綿ショーツ 深履き 黒 パンツ (JP, アルファベット, L, ブラック)\",10,2,10%,1500,2
"""
            (root / "amzon-csv" / "BusinessReport-2026-03.csv").write_text(business, encoding="utf-8")

            payload = build_dashboard(root, period_start="2026-03-01", period_end="2026-03-31")
            amazon_products = [entry for entry in payload["products"] if entry["marketplace"] == "amazon"]

            self.assertEqual(len(amazon_products), 1)
            product = payload["productDetails"][amazon_products[0]["id"]]
            self.assertEqual(product["summary"]["sales"], 2500.0)
            self.assertEqual(product["summary"]["units"], 3.0)
            self.assertEqual(len(product["variants"]), 2)

    def test_amazon_business_report_preserves_variant_size_for_transaction_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            business = """（親）ASIN,（子）ASIN,タイトル,セッション数 - 合計,注文された商品点数,ユニットセッション率,注文商品の売上額,注文品目総数
PARENT1,CHILD1,"テスト商品 ロングタイトル (JP, アルファベット, M, ブラック)",10,1,10%,1000,1
PARENT1,CHILD2,"テスト商品 ロングタイトル (JP, アルファベット, L, ブラック)",10,1,10%,1000,1
"""
            transactions = """日付,注文番号,商品の詳細,商品価格合計,プロモーション割引合計,Amazon手数料,合計 (JPY),トランザクションの種類,トランザクションステータス,数量
2026/03/05,ORDER-1,テスト商品,1000,0,-100,900,注文に対する支払い,完了,1
2026/03/06,ORDER-2,テスト商品,1200,0,-100,1100,注文に対する支払い,完了,1
"""
            (root / "amzon-csv" / "BusinessReport-2026-03.csv").write_text(business, encoding="utf-8")
            (root / "amzon-csv" / "取引-20260301_20260331.csv").write_text(transactions, encoding="utf-8")

            payload = build_dashboard(root, period_start="2026-03-01", period_end="2026-03-31")
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "amazon"
            )

            sizes = [variant["size"] for variant in product["variants"]]
            self.assertEqual(sizes, ["M", "L"])
            self.assertEqual(product["summary"]["sales"], 2200.0)

    def test_amazon_parent_summary_variant_is_dropped_when_child_variants_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            business = """（親）ASIN,（子）ASIN,タイトル,セッション数 - 合計,注文された商品点数,ユニットセッション率,注文商品の売上額,注文品目総数
PARENT1,PARENT1,テスト商品 親タイトル,10,2,10%,2200,2
PARENT1,CHILD1,"テスト商品 親タイトル (JP, アルファベット, M, ブラック)",10,1,10%,1000,1
PARENT1,CHILD2,"テスト商品 親タイトル (JP, アルファベット, L, ブラック)",10,1,10%,1200,1
"""
            (root / "amzon-csv" / "BusinessReport-2026-03.csv").write_text(business, encoding="utf-8")

            payload = build_dashboard(root, period_start="2026-03-01", period_end="2026-03-31")
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "amazon"
            )

            labels = [variant["label"] for variant in product["variants"]]
            self.assertEqual(labels, ["ブラック / M", "ブラック / L"])

    def test_rakuten_api_orders_build_product_and_variant_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            api_orders = [
                {
                    "orderNumber": "100-0000000-0000001",
                    "orderDatetime": "2026-03-05T10:00:00+0900",
                    "PackageModelList": [
                        {
                            "ItemModelList": [
                                {
                                    "itemName": "楽天テスト商品",
                                    "manageNumber": "prod-1",
                                    "units": 2,
                                    "price": 1500,
                                    "selectedChoice": "カラー:ブラック|サイズ:M",
                                },
                                {
                                    "itemName": "楽天テスト商品",
                                    "manageNumber": "prod-1",
                                    "units": 1,
                                    "price": 1500,
                                    "selectedChoice": "カラー:ブラック|サイズ:L",
                                },
                            ]
                        }
                    ],
                },
                {
                    "orderNumber": "100-0000000-0000002",
                    "orderDatetime": "2026-03-06T11:00:00+0900",
                    "PackageModelList": [
                        {
                            "ItemModelList": [
                                {
                                    "itemName": "楽天テスト商品",
                                    "manageNumber": "prod-1",
                                    "units": 1,
                                    "price": 1800,
                                    "skuInfo": "色:ベージュ|サイズ:M",
                                }
                            ]
                        }
                    ],
                },
            ]

            with mock.patch("eanalytics.dashboard.rakuten_api_enabled", return_value=True):
                with mock.patch("eanalytics.dashboard.fetch_rakuten_orders", return_value=api_orders) as fetch_mock:
                    payload = build_dashboard(root, period_start="2026-03-01", period_end="2026-03-31")

            fetch_mock.assert_called_once_with("2026-03-01", "2026-03-31")
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "rakuten"
            )

            self.assertEqual(product["summary"]["sales"], 6300.0)
            self.assertEqual(product["summary"]["orders"], 2.0)
            self.assertEqual(product["summary"]["units"], 4.0)
            self.assertEqual([item["label"] for item in product["sizeDistribution"]], ["M", "L"])
            self.assertEqual([item["label"] for item in product["colorDistribution"]], ["ブラック", "ベージュ"])
            self.assertTrue(all(variant["timelineAvailable"] for variant in product["variants"]))

    def test_rakuten_api_error_is_exposed_in_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()

            with mock.patch("eanalytics.dashboard.rakuten_api_enabled", return_value=True):
                with mock.patch("eanalytics.dashboard.fetch_rakuten_orders", side_effect=Exception("boom")):
                    payload = build_dashboard(root, period_start="2026-03-01", period_end="2026-03-31")

            rakuten_summary = payload["summary"]["rakuten"]
            self.assertEqual(rakuten_summary["sales"], 0.0)
            self.assertTrue(any("楽天API" in note for note in payload["notes"]))

    def test_rakuten_order_csv_filters_by_date_skips_900_and_merges_same_sku(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "amzon-csv").mkdir()
            (root / "rakuten-csv").mkdir()
            order_csv = """注文番号,ステータス,注文日時,注文日,商品明細ID,商品ID,商品名,商品管理番号,単価,個数,項目・選択肢,SKU管理番号,SKU情報,商品毎税込価格
436667-20260301-0000000001,700,2026-03-01 10:00:00,2026-03-01,1,1001,短い商品名,prod-1,1000,1,,sku-1,"カラー:ブラック\n+サイズ:M",1000
436667-20260302-0000000002,900,2026-03-02 10:00:00,2026-03-02,2,1001,短い商品名,prod-1,1000,2,,sku-1,"カラー:ブラック\n+サイズ:M",1000
436667-20260303-0000000003,700,2026-03-03 10:00:00,2026-03-03,3,1001,もっと長い商品名です,prod-1,1200,2,,sku-1,"カラー:ブラック\n+サイズ:M",1200
"""
            (root / "rakuten-csv" / "2026-3.csv").write_text(order_csv, encoding="cp932")

            payload = build_dashboard(root, period_start="2026-03-01", period_end="2026-03-31")
            product = next(
                payload["productDetails"][entry["id"]]
                for entry in payload["products"]
                if entry["marketplace"] == "rakuten"
            )

            self.assertEqual(product["summary"]["sales"], 3400.0)
            self.assertEqual(product["summary"]["units"], 3.0)
            self.assertEqual(product["summary"]["orders"], 2.0)
            self.assertEqual(product["name"], "もっと長い商品名です")
            self.assertEqual(len(product["variants"]), 1)
            self.assertEqual(product["variants"][0]["id"], "sku-1")
            self.assertEqual(
                product["variants"][0]["timeline"],
                [
                    {"date": "2026-03-01", "sales": 1000.0, "units": 1.0},
                    {"date": "2026-03-03", "sales": 2400.0, "units": 2.0},
                ],
            )


if __name__ == "__main__":
    unittest.main()
