from pathlib import Path
import shutil
import tempfile
import unittest

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

    def test_rakuten_product_has_limitations(self) -> None:
        rakuten_products = [
            self.payload["productDetails"][product["id"]]
            for product in self.payload["products"]
            if product["marketplace"] == "rakuten"
        ]
        candidate = next(product for product in rakuten_products if product["limitations"])
        self.assertIn("楽天", candidate["limitations"][0])

    def test_sources_are_registered(self) -> None:
        source_ids = {source["id"] for source in self.payload["sources"]}
        self.assertIn("amazon_transactions", source_ids)
        self.assertIn("rakuten_store", source_ids)

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
            rakuten_src = next(path for path in (root / "rakuten-csv").iterdir() if "SKU別売上" in path.name)

            shutil.copy2(business_src, base_root / "amzon-csv" / business_src.name)
            shutil.copy2(rakuten_src, base_root / "rakuten-csv" / rakuten_src.name)

            shutil.copy2(business_src, duplicate_root / "amzon-csv" / business_src.name)
            shutil.copy2(business_src, duplicate_root / "amzon-csv" / "BusinessReport-duplicate.csv")
            shutil.copy2(rakuten_src, duplicate_root / "rakuten-csv" / rakuten_src.name)
            shutil.copy2(rakuten_src, duplicate_root / "rakuten-csv" / "20250901_20250930_日次_SKU別売上データ_duplicate.csv")

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


if __name__ == "__main__":
    unittest.main()
