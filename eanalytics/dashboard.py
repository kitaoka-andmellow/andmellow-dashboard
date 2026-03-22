from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .parsers import (
    list_matching_files,
    normalize_product_text,
    normalize_spaces,
    parse_date,
    parse_number,
    parse_percentage,
    read_csv_rows,
    read_csv_rows_matching,
    read_xlsx_rows,
    slugify,
)


def safe_div(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return numerator / denominator


def round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def strip_trailing_variant(title: str) -> str:
    return normalize_spaces(re.sub(r"\([^)]*\)\s*$", "", title or ""))


def parse_amazon_variant(title: str, fallback: str = "") -> dict[str, str | None]:
    title = normalize_spaces(title)
    base = strip_trailing_variant(title) or fallback
    match = re.search(r"\(([^()]*)\)\s*$", title)
    size = None
    color = None
    if match:
        parts = [normalize_spaces(part) for part in match.group(1).split(",") if normalize_spaces(part)]
        if len(parts) == 2:
            color, size = parts
        elif len(parts) >= 4:
            size = parts[-2]
            color = parts[-1]
        elif len(parts) == 1:
            size = parts[0]
    label_parts = [part for part in (color, size) if part]
    variant_label = " / ".join(label_parts) if label_parts else "未設定"
    return {
        "base": base,
        "size": size,
        "color": color,
        "variant_label": variant_label,
    }


def clean_rakuten_variant_text(value: str | None) -> str | None:
    if not value:
        return None
    text = normalize_spaces(value)
    text = re.sub(r"[（(][^()（）]*[)）]", "", text)
    text = normalize_spaces(text)
    return text or None


def resolve_rakuten_color_aliases(labels: list[str | None]) -> dict[str, str]:
    cleaned_labels = sorted({label for label in (clean_rakuten_variant_text(item) for item in labels) if label})
    aliases: dict[str, str] = {}
    for label in cleaned_labels:
        aliases[label] = label
    for label in cleaned_labels:
        if not re.search(r"】$", label):
            continue
        candidates = [candidate for candidate in cleaned_labels if candidate.startswith(label) and candidate != label]
        if candidates:
            aliases[label] = max(candidates, key=len)
    return aliases


def collapse_rakuten_variants(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    color_aliases = resolve_rakuten_color_aliases([variant.get("color") for variant in variants])
    collapsed: dict[tuple[str, str], dict[str, Any]] = {}
    for variant in variants:
        color_key = clean_rakuten_variant_text(variant.get("color")) or "未設定"
        color = color_aliases.get(color_key, color_key)
        size = normalize_spaces(str(variant.get("size") or "")) or "未設定"
        key = (color, size)
        bucket = collapsed.setdefault(
            key,
            {
                "id": variant.get("id"),
                "title": variant.get("title"),
                "label": " / ".join(part for part in (color, size) if part and part != "未設定") or "未設定",
                "size": None if size == "未設定" else size,
                "color": None if color == "未設定" else color,
                "sales": 0.0,
                "orders": 0.0,
                "units": 0.0,
                "sessions": 0.0,
                "conversionRate": None,
            },
        )
        bucket["sales"] += float(variant.get("sales", 0))
        bucket["orders"] += float(variant.get("orders", 0))
        bucket["units"] += float(variant.get("units", 0))
        bucket["sessions"] += float(variant.get("sessions", 0))
    return [
        {
            **variant,
            "sales": round(variant["sales"], 2),
            "orders": round(variant["orders"], 2),
            "units": round(variant["units"], 2),
            "sessions": round(variant["sessions"], 2),
        }
        for variant in collapsed.values()
    ]


def build_distribution(variants: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    total_units = sum(variant.get("units", 0) for variant in variants)
    for variant in variants:
        label = normalize_spaces(str(variant.get(field) or "")) or "未設定"
        bucket = buckets.setdefault(
            label,
            {"label": label, "sales": 0.0, "units": 0.0, "orders": 0.0},
        )
        bucket["sales"] += float(variant.get("sales", 0))
        bucket["units"] += float(variant.get("units", 0))
        bucket["orders"] += float(variant.get("orders", 0))
    items = sorted(
        buckets.values(),
        key=lambda item: (item["units"], item["sales"], item["label"]),
        reverse=True,
    )
    for item in items:
        item["share"] = round_metric(safe_div(item["units"], total_units))
    return items


def summarize_product(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": detail["id"],
        "marketplace": detail["marketplace"],
        "name": detail["name"],
        "sales": round(detail["summary"]["sales"], 2),
        "orders": round(detail["summary"]["orders"], 2),
        "units": round(detail["summary"]["units"], 2),
        "sessions": round(detail["summary"].get("sessions", 0), 2),
        "conversionRate": detail["summary"].get("conversionRate"),
        "adCost": detail["summary"].get("adCost"),
        "adRatio": detail["summary"].get("adRatio"),
        "bundleRate": detail["summary"].get("bundleRate"),
        "variantCount": detail["summary"].get("variantCount", 0),
        "hasTimeline": bool(detail.get("timeline")),
        "hasTransactions": bool(detail.get("transactions")),
        "limitations": detail.get("limitations", []),
    }


def source_entry(
    source_id: str,
    label: str,
    path: Path | None,
    status: str,
    records: int = 0,
    message: str = "",
    paths: list[Path] | None = None,
    duplicates_removed: int = 0,
) -> dict[str, Any]:
    normalized_paths = [str(item) for item in (paths or ([path] if path else []))]
    return {
        "id": source_id,
        "label": label,
        "path": normalized_paths[0] if normalized_paths else None,
        "paths": normalized_paths,
        "status": status,
        "records": records,
        "message": message,
        "duplicatesRemoved": duplicates_removed,
    }


def exact_row_signature(row: dict[str, str], keys: list[str]) -> tuple[str, ...]:
    return tuple(normalize_spaces(row.get(key, "")) for key in keys)


def build_amazon_marketplace(root: Path) -> dict[str, Any]:
    directory = root / "amzon-csv"
    sources: list[dict[str, Any]] = []
    notes: list[str] = []
    families: dict[str, dict[str, Any]] = {}
    parent_names: dict[str, str] = {}
    timeline: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"sales": 0.0, "orders": set(), "adCost": 0.0, "fees": 0.0}
    )
    ad_cost_available = False
    transactions_paths = list_matching_files(directory, ["取引"], [".csv"])
    business_paths = list_matching_files(directory, ["BusinessReport"], [".csv"])
    ads_paths = list_matching_files(directory, ["広告"], [".xlsx"])

    if business_paths:
        business_rows: list[dict[str, str]] = []
        seen_business_rows: set[tuple[str, ...]] = set()
        business_duplicates_removed = 0
        for business_path in business_paths:
            for row in read_csv_rows(business_path):
                signature = exact_row_signature(
                    row,
                    [
                        "（親）ASIN",
                        "（子）ASIN",
                        "タイトル",
                        "注文された商品点数",
                        "注文商品の売上額",
                        "注文品目総数",
                        "セッション数 - 合計",
                    ],
                )
                if signature in seen_business_rows:
                    business_duplicates_removed += 1
                    continue
                seen_business_rows.add(signature)
                business_rows.append(row)
        sources.append(
            source_entry(
                "amazon_business",
                "Amazon 商品別レポート",
                business_paths[0],
                "loaded" if business_rows else "empty",
                len(business_rows),
                f"{len(business_paths)}ファイルの親ASIN/子ASIN単位の販売実績を読み込みました。"
                if business_rows
                else "商品別レポートに行がありません。",
                paths=business_paths,
                duplicates_removed=business_duplicates_removed,
            )
        )
        by_parent: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in business_rows:
            parent = row.get("（親）ASIN", "").strip() or row.get("（子）ASIN", "").strip()
            if parent:
                by_parent[parent].append(row)
        for parent, rows in by_parent.items():
            titled = [strip_trailing_variant(row.get("タイトル", "")) for row in rows if strip_trailing_variant(row.get("タイトル", ""))]
            parent_names[parent] = min(titled, key=len) if titled else f"ASIN {parent}"
        for row in business_rows:
            parent = row.get("（親）ASIN", "").strip() or row.get("（子）ASIN", "").strip()
            child = row.get("（子）ASIN", "").strip()
            family_name = parent_names.get(parent, child or "Amazon商品")
            family_key = normalize_product_text(family_name) or parent or child
            detail = families.setdefault(
                family_key,
                {
                    "id": f"amazon-{slugify(family_name)}",
                    "marketplace": "amazon",
                    "name": family_name,
                    "summary": {
                        "sales": 0.0,
                        "orders": 0.0,
                        "units": 0.0,
                        "sessions": 0.0,
                        "conversionRate": None,
                        "adCost": None,
                        "adRatio": None,
                        "bundleRate": None,
                        "variantCount": 0,
                    },
                    "sizeDistribution": [],
                    "colorDistribution": [],
                    "variants": [],
                    "timeline": [],
                    "transactions": [],
                    "limitations": [],
                    "_aliases": set(),
                    "_orders": set(),
                    "_timeline": defaultdict(lambda: {"sales": 0.0, "orders": set()}),
                },
            )
            if len(family_name) < len(detail["name"]):
                detail["name"] = family_name
            title = row.get("タイトル", "").strip()
            variant_meta = parse_amazon_variant(title, family_name)
            sales = parse_number(row.get("注文商品の売上額"))
            units = parse_number(row.get("注文品目総数"))
            orders = parse_number(row.get("注文された商品点数"))
            sessions = parse_number(row.get("セッション数 - 合計"))
            detail["summary"]["sales"] += sales
            detail["summary"]["orders"] += orders
            detail["summary"]["units"] += units
            detail["summary"]["sessions"] += sessions
            detail["_aliases"].add(normalize_product_text(family_name))
            if title:
                detail["_aliases"].add(normalize_product_text(strip_trailing_variant(title)))
            detail["variants"].append(
                {
                    "id": child or f"{detail['id']}-variant-{len(detail['variants']) + 1}",
                    "title": title or family_name,
                    "label": variant_meta["variant_label"] or child or "未設定",
                    "size": variant_meta["size"],
                    "color": variant_meta["color"],
                    "sales": round(sales, 2),
                    "orders": round(orders, 2),
                    "units": round(units, 2),
                    "sessions": round(sessions, 2),
                    "conversionRate": round_metric(parse_percentage(row.get("ユニットセッション率"))),
                    "childAsin": child or None,
                }
            )
    else:
        sources.append(
            source_entry(
                "amazon_business",
                "Amazon 商品別レポート",
                None,
                "missing",
                0,
                "BusinessReport CSV が見つかりませんでした。",
                paths=[],
            )
        )
        notes.append("Amazon の商品別レポートが無いため、商品ごとのサイズ・色分布は表示できません。")

    alias_index: list[tuple[str, str]] = []
    for family_key, detail in families.items():
        for alias in detail["_aliases"]:
            if alias:
                alias_index.append((alias, family_key))
    alias_index.sort(key=lambda item: len(item[0]), reverse=True)

    def match_family(product_detail: str) -> str | None:
        normalized = normalize_product_text(product_detail)
        if not normalized:
            return None
        for alias, family_key in alias_index:
            if normalized in alias or alias in normalized:
                return family_key
        return None

    order_line_counts: dict[str, int] = defaultdict(int)
    if transactions_paths:
        transaction_rows: list[dict[str, str]] = []
        seen_transaction_rows: set[tuple[str, ...]] = set()
        transaction_duplicates_removed = 0
        for transactions_path in transactions_paths:
            for row in read_csv_rows(transactions_path):
                signature = exact_row_signature(
                    row,
                    [
                        "日付",
                        "注文番号",
                        "商品の詳細",
                        "商品価格合計",
                        "プロモーション割引合計",
                        "合計 (JPY)",
                        "トランザクションの種類",
                    ],
                )
                if signature in seen_transaction_rows:
                    transaction_duplicates_removed += 1
                    continue
                seen_transaction_rows.add(signature)
                transaction_rows.append(row)
        sources.append(
            source_entry(
                "amazon_transactions",
                "Amazon 取引CSV",
                transactions_paths[0],
                "loaded" if transaction_rows else "empty",
                len(transaction_rows),
                f"{len(transactions_paths)}ファイルの注文単位取引明細を読み込みました。"
                if transaction_rows
                else "取引CSVに行がありません。",
                paths=transactions_paths,
                duplicates_removed=transaction_duplicates_removed,
            )
        )
        for row in transaction_rows:
            if row.get("トランザクションの種類") != "注文に対する支払い":
                continue
            date = parse_date(row.get("日付"))
            order_id = normalize_spaces(row.get("注文番号", ""))
            if not date or not order_id:
                continue
            gross_sales = parse_number(row.get("商品価格合計"))
            promo_discount = parse_number(row.get("プロモーション割引合計"))
            sales = gross_sales + promo_discount
            fee = abs(parse_number(row.get("Amazon手数料")))
            settlement = parse_number(row.get("合計 (JPY)"))
            product_detail = normalize_spaces(row.get("商品の詳細", ""))
            status = normalize_spaces(row.get("トランザクションステータス", ""))
            family_key = match_family(product_detail)
            timeline[date]["sales"] += sales
            timeline[date]["fees"] += fee
            timeline[date]["orders"].add(order_id)
            order_line_counts[order_id] += 1
            if family_key and family_key in families:
                detail = families[family_key]
                detail["_orders"].add(order_id)
                detail["_timeline"][date]["sales"] += sales
                detail["_timeline"][date]["orders"].add(order_id)
                detail["transactions"].append(
                    {
                        "date": date,
                        "orderId": order_id,
                        "status": status,
                        "detail": product_detail,
                        "grossSales": round(gross_sales, 2),
                        "promotionDiscount": round(abs(min(promo_discount, 0)), 2),
                        "sales": round(sales, 2),
                        "fee": round(fee, 2),
                        "settlement": round(settlement, 2),
                    }
                )
    else:
        sources.append(
            source_entry(
                "amazon_transactions",
                "Amazon 取引CSV",
                None,
                "missing",
                0,
                "取引CSVが見つかりませんでした。",
                paths=[],
            )
        )
        notes.append("Amazon の取引CSVが無いため、商品ごとのトランザクションとセット購入率は表示できません。")

    if ads_paths:
        records = 0
        ad_duplicates_removed = 0
        seen_ad_rows: set[tuple[str, ...]] = set()
        for ads_path in ads_paths:
            ads_rows = read_xlsx_rows(ads_path)
            if len(ads_rows) <= 1:
                continue
            headers = ads_rows[0]
            for row in ads_rows[1:]:
                if not any(str(cell).strip() for cell in row):
                    continue
                payload = {
                    headers[index]: row[index].strip() if index < len(row) else ""
                    for index in range(len(headers))
                }
                signature = tuple(normalize_spaces(str(value)) for value in payload.values())
                if signature in seen_ad_rows:
                    ad_duplicates_removed += 1
                    continue
                seen_ad_rows.add(signature)
                date = parse_date(payload.get("日付"))
                cost = parse_number(payload.get("費用"))
                if date:
                    timeline[date]["adCost"] += cost
                    ad_cost_available = True
                records += 1
        status = "loaded" if records else "empty"
        message = (
            f"{len(ads_paths)}ファイルのスポンサープロダクト広告費用を読み込みました。"
            if records
            else "広告レポートはヘッダーのみでした。"
        )
        sources.append(
            source_entry(
                "amazon_ads",
                "Amazon 広告レポート",
                ads_paths[0],
                status,
                records,
                message,
                paths=ads_paths,
                duplicates_removed=ad_duplicates_removed,
            )
        )
        if not records:
            notes.append("Amazon の広告レポートに実データが無かったため、Amazon 広告費率は未算出です。")
    else:
        sources.append(
            source_entry(
                "amazon_ads",
                "Amazon 広告レポート",
                None,
                "missing",
                0,
                "広告レポートが見つかりませんでした。",
                paths=[],
            )
        )
        notes.append("Amazon の広告レポートが無いため、広告費率は未算出です。")

    multi_item_orders = {order_id for order_id, count in order_line_counts.items() if count > 1}
    for detail in families.values():
        detail["transactions"].sort(key=lambda item: (item["date"], item["orderId"]), reverse=True)
        detail["transactions"] = detail["transactions"][:40]
        detail["timeline"] = [
            {
                "date": date,
                "sales": round(values["sales"], 2),
                "orders": len(values["orders"]),
            }
            for date, values in sorted(detail["_timeline"].items())
        ]
        bundle_orders = len(detail["_orders"] & multi_item_orders)
        order_count = len(detail["_orders"])
        detail["summary"]["bundleRate"] = round_metric(safe_div(bundle_orders, order_count))
        detail["summary"]["variantCount"] = len(detail["variants"])
        detail["summary"]["conversionRate"] = round_metric(
            safe_div(detail["summary"]["units"], detail["summary"]["sessions"])
        )
        detail["sizeDistribution"] = build_distribution(detail["variants"], "size")
        detail["colorDistribution"] = build_distribution(detail["variants"], "color")
        detail["variants"].sort(key=lambda variant: (variant["sales"], variant["units"]), reverse=True)
        if detail["summary"]["adCost"] is None:
            detail["limitations"].append("Amazon の広告レポートは商品別費用を含まないため、商品単位の広告費率は未算出です。")
        if not detail["timeline"]:
            detail["limitations"].append("この商品に紐づく Amazon 取引が見つからず、日次推移は表示していません。")
        if not detail["transactions"]:
            detail["limitations"].append("この商品に紐づく Amazon トランザクションが見つかりませんでした。")
        detail["summary"]["sales"] = round(detail["summary"]["sales"], 2)
        detail["summary"]["orders"] = round(detail["summary"]["orders"], 2)
        detail["summary"]["units"] = round(detail["summary"]["units"], 2)
        detail["summary"]["sessions"] = round(detail["summary"]["sessions"], 2)
        detail.pop("_aliases", None)
        detail.pop("_orders", None)
        detail.pop("_timeline", None)

    total_sales = sum(day["sales"] for day in timeline.values())
    total_orders = len(order_line_counts)
    total_units = sum(detail["summary"]["units"] for detail in families.values())
    total_ad_cost = sum(day["adCost"] for day in timeline.values())
    total_fees = sum(day["fees"] for day in timeline.values())
    summary = {
        "sales": round(total_sales, 2),
        "orders": total_orders,
        "units": round(total_units, 2),
        "fees": round(total_fees, 2),
        "adCost": round(total_ad_cost, 2) if ad_cost_available else None,
        "adRatio": round_metric(safe_div(total_ad_cost, total_sales)) if ad_cost_available else None,
        "bundleRate": round_metric(safe_div(len(multi_item_orders), total_orders)),
        "averageOrderValue": round_metric(safe_div(total_sales, total_orders)),
    }
    return {
        "marketplace": "amazon",
        "summary": summary,
        "timeline": {
            date: {
                "sales": round(day["sales"], 2),
                "orders": len(day["orders"]),
                "adCost": round(day["adCost"], 2),
            }
            for date, day in timeline.items()
        },
        "products": list(families.values()),
        "notes": notes,
        "sources": sources,
    }


def build_rakuten_marketplace(root: Path) -> dict[str, Any]:
    directory = root / "rakuten-csv"
    sources: list[dict[str, Any]] = []
    notes: list[str] = []
    families: dict[str, dict[str, Any]] = {}
    timeline: dict[str, dict[str, Any]] = defaultdict(lambda: {"sales": 0.0, "orders": 0.0, "adCost": 0.0})
    ad_cost_available = False
    sku_paths = list_matching_files(directory, ["SKU別売上"], [".csv"])
    store_paths = list_matching_files(directory, ["店舗", "データ"], [".csv"])
    points_paths = list_matching_files(directory, ["商品", "ポイント"], [".csv"])
    campaign_paths = list_matching_files(directory, ["キャンペーン"], [".csv"])

    promoted_sales_by_product: dict[str, float] = defaultdict(float)
    if points_paths:
        points_rows: list[dict[str, str]] = []
        seen_points_rows: set[tuple[str, ...]] = set()
        points_duplicates_removed = 0
        for points_path in points_paths:
            for row in read_csv_rows_matching(
                points_path,
                lambda header: header and header[0] == "日付" and "運用型ポイント変倍経由売上金額" in header,
            ):
                signature = exact_row_signature(
                    row,
                    ["日付", "商品名", "商品管理番号", "運用型ポイント変倍経由売上金額", "運用型ポイント変倍倍率"],
                )
                if signature in seen_points_rows:
                    points_duplicates_removed += 1
                    continue
                seen_points_rows.add(signature)
                points_rows.append(row)
        nonempty_rows = [row for row in points_rows if normalize_spaces(row.get("商品名", ""))]
        for row in nonempty_rows:
            key = normalize_product_text(row.get("商品名", ""))
            promoted_sales_by_product[key] += parse_number(row.get("運用型ポイント変倍経由売上金額"))
        sources.append(
            source_entry(
                "rakuten_points",
                "楽天 商品データ(運用型ポイント)",
                points_paths[0],
                "loaded" if nonempty_rows else "empty",
                len(nonempty_rows),
                f"{len(points_paths)}ファイルの商品別ポイント経由売上を読み込みました。"
                if nonempty_rows
                else "商品別のポイント経由売上データは空でした。",
                paths=points_paths,
                duplicates_removed=points_duplicates_removed,
            )
        )
        if not nonempty_rows:
            notes.append("楽天の運用型ポイント商品データに明細が無かったため、商品別の広告寄与は未表示です。")
    else:
        sources.append(
            source_entry(
                "rakuten_points",
                "楽天 商品データ(運用型ポイント)",
                None,
                "missing",
                0,
                "商品データ_運用型ポイント CSV が見つかりませんでした。",
                paths=[],
            )
        )

    if sku_paths:
        sku_rows: list[dict[str, str]] = []
        seen_sku_rows: set[tuple[str, ...]] = set()
        sku_duplicates_removed = 0
        for sku_path in sku_paths:
            for row in read_csv_rows_matching(
                sku_path,
                lambda header: header and header[0] == "カタログID" and "売上金額" in header,
            ):
                signature = exact_row_signature(
                    row,
                    [
                        "商品管理番号",
                        "SKU管理番号",
                        "SKU項目1",
                        "SKU項目2",
                        "SKU項目3",
                        "SKU項目4",
                        "SKU項目5",
                        "SKU項目6",
                        "売上金額",
                        "売上件数",
                        "売上個数",
                    ],
                )
                if signature in seen_sku_rows:
                    sku_duplicates_removed += 1
                    continue
                seen_sku_rows.add(signature)
                sku_rows.append(row)
        sources.append(
            source_entry(
                "rakuten_sku",
                "楽天 SKU別売上データ",
                sku_paths[0],
                "loaded" if sku_rows else "empty",
                len(sku_rows),
                f"{len(sku_paths)}ファイルのSKU単位売上を読み込みました。"
                if sku_rows
                else "SKU別売上データに行がありません。",
                paths=sku_paths,
                duplicates_removed=sku_duplicates_removed,
            )
        )
        for row in sku_rows:
            name = normalize_spaces(row.get("商品名", "")) or "楽天商品"
            product_code = normalize_spaces(row.get("商品管理番号", "")) or slugify(name)
            family_key = product_code or normalize_product_text(name)
            detail = families.setdefault(
                family_key,
                {
                    "id": f"rakuten-{product_code}",
                    "marketplace": "rakuten",
                    "name": name,
                    "summary": {
                        "sales": 0.0,
                        "orders": 0.0,
                        "units": 0.0,
                        "sessions": 0.0,
                        "conversionRate": None,
                        "adCost": None,
                        "adRatio": None,
                        "bundleRate": None,
                        "variantCount": 0,
                        "promotedSales": 0.0,
                    },
                    "sizeDistribution": [],
                    "colorDistribution": [],
                    "variants": [],
                    "timeline": [],
                    "transactions": [],
                    "limitations": [
                        "楽天の SKU 別売上 CSV は期間集計のため、商品別の日次推移は未表示です。",
                        "楽天の手元CSVには注文単位データが無いため、商品別のセット購入率は未算出です。",
                    ],
                },
            )
            sku_items = [
                normalize_spaces(row.get(f"SKU項目{index}", ""))
                for index in range(1, 7)
                if normalize_spaces(row.get(f"SKU項目{index}", ""))
            ]
            size = normalize_spaces(sku_items[1]) if len(sku_items) > 1 else None
            color = clean_rakuten_variant_text(sku_items[0]) if sku_items else None
            sales = parse_number(row.get("売上金額"))
            orders = parse_number(row.get("売上件数"))
            units = parse_number(row.get("売上個数"))
            detail["summary"]["sales"] += sales
            detail["summary"]["orders"] += orders
            detail["summary"]["units"] += units
            detail["variants"].append(
                {
                    "id": normalize_spaces(row.get("SKU管理番号", "")) or f"{detail['id']}-variant-{len(detail['variants']) + 1}",
                    "title": " / ".join(sku_items) if sku_items else name,
                    "label": " / ".join(part for part in (color, size) if part) if (color or size) else "未設定",
                    "size": size,
                    "color": color,
                    "sales": round(sales, 2),
                    "orders": round(orders, 2),
                    "units": round(units, 2),
                    "sessions": 0,
                    "conversionRate": None,
                }
            )
        notes.append("楽天の商品別詳細は SKU 別売上 CSV から生成しているため、日次推移とセット購入率は今のデータでは出していません。")
    else:
        sources.append(
            source_entry(
                "rakuten_sku",
                "楽天 SKU別売上データ",
                None,
                "missing",
                0,
                "SKU別売上データ CSV が見つかりませんでした。",
                paths=[],
            )
        )
        notes.append("楽天の SKU 別売上データが無いため、商品ごとのサイズ・色分布は表示できません。")

    if store_paths:
        store_rows: list[dict[str, str]] = []
        seen_store_rows: set[tuple[str, ...]] = set()
        store_duplicates_removed = 0
        for store_path in store_paths:
            for row in read_csv_rows_matching(
                store_path,
                lambda header: header and header[0] == "日付" and "売上金額" in header and "デバイス" in header,
            ):
                signature = exact_row_signature(
                    row,
                    ["日付", "デバイス", "売上金額", "売上件数", "運用型ポイント変倍経由ポイント付与料"],
                )
                if signature in seen_store_rows:
                    store_duplicates_removed += 1
                    continue
                seen_store_rows.add(signature)
                store_rows.append(row)
        daily_rows = [row for row in store_rows if normalize_spaces(row.get("デバイス")) == "すべて"]
        sources.append(
            source_entry(
                "rakuten_store",
                "楽天 店舗データ",
                store_paths[0],
                "loaded" if daily_rows else "empty",
                len(daily_rows),
                f"{len(store_paths)}ファイルの日次店舗データを読み込みました。"
                if daily_rows
                else "店舗データに日次行がありません。",
                paths=store_paths,
                duplicates_removed=store_duplicates_removed,
            )
        )
        for row in daily_rows:
            date = parse_date(row.get("日付"))
            if not date:
                continue
            sales = parse_number(row.get("売上金額"))
            orders = parse_number(row.get("売上件数"))
            raw_ad_cost = normalize_spaces(row.get("運用型ポイント変倍経由ポイント付与料", ""))
            ad_cost = parse_number(row.get("運用型ポイント変倍経由ポイント付与料"))
            if raw_ad_cost:
                ad_cost_available = True
            timeline[date]["sales"] += sales
            timeline[date]["orders"] += orders
            timeline[date]["adCost"] += ad_cost
        if not ad_cost_available:
            notes.append("楽天の店舗データに広告費列の実値が無かったため、楽天の広告費率は未算出です。")
    else:
        sources.append(
            source_entry(
                "rakuten_store",
                "楽天 店舗データ",
                None,
                "missing",
                0,
                "店舗データ CSV が見つかりませんでした。",
                paths=[],
            )
        )
        notes.append("楽天の店舗データが無いため、楽天の日次売上推移と広告費率は未表示です。")

    if campaign_paths:
        campaign_rows: list[dict[str, str]] = []
        seen_campaign_rows: set[tuple[str, ...]] = set()
        campaign_duplicates_removed = 0
        for campaign_path in campaign_paths:
            for row in read_csv_rows_matching(
                campaign_path,
                lambda header: header and header[0] == "キャンペーン種類" and "キャンペーン名" in header,
            ):
                signature = exact_row_signature(row, ["キャンペーン種類", "キャンペーン名", "開始日時", "終了日時"])
                if signature in seen_campaign_rows:
                    campaign_duplicates_removed += 1
                    continue
                seen_campaign_rows.add(signature)
                campaign_rows.append(row)
        sources.append(
            source_entry(
                "rakuten_campaign",
                "楽天 キャンペーン一覧",
                campaign_paths[0],
                "loaded" if campaign_rows else "empty",
                len(campaign_rows),
                f"{len(campaign_paths)}ファイルのキャンペーン一覧を読み込みました。"
                if campaign_rows
                else "キャンペーン一覧に行がありません。",
                paths=campaign_paths,
                duplicates_removed=campaign_duplicates_removed,
            )
        )
    else:
        sources.append(
            source_entry(
                "rakuten_campaign",
                "楽天 キャンペーン一覧",
                None,
                "missing",
                0,
                "キャンペーン一覧 CSV が見つかりませんでした。",
                paths=[],
            )
        )

    for detail in families.values():
        if detail["marketplace"] == "rakuten":
            detail["variants"] = collapse_rakuten_variants(detail["variants"])
        detail["summary"]["variantCount"] = len(detail["variants"])
        detail["summary"]["promotedSales"] = round(
            promoted_sales_by_product.get(normalize_product_text(detail["name"]), 0.0),
            2,
        )
        detail["summary"]["sales"] = round(detail["summary"]["sales"], 2)
        detail["summary"]["orders"] = round(detail["summary"]["orders"], 2)
        detail["summary"]["units"] = round(detail["summary"]["units"], 2)
        detail["sizeDistribution"] = build_distribution(detail["variants"], "size")
        detail["colorDistribution"] = build_distribution(detail["variants"], "color")
        detail["variants"].sort(key=lambda variant: (variant["sales"], variant["units"]), reverse=True)

    total_sales = sum(day["sales"] for day in timeline.values())
    total_orders = sum(day["orders"] for day in timeline.values())
    total_units = sum(detail["summary"]["units"] for detail in families.values())
    total_ad_cost = sum(day["adCost"] for day in timeline.values())
    summary = {
        "sales": round(total_sales, 2),
        "orders": round(total_orders, 2),
        "units": round(total_units, 2),
        "fees": 0.0,
        "adCost": round(total_ad_cost, 2) if ad_cost_available else None,
        "adRatio": round_metric(safe_div(total_ad_cost, total_sales)) if ad_cost_available else None,
        "bundleRate": None,
        "averageOrderValue": round_metric(safe_div(total_sales, total_orders)),
    }
    return {
        "marketplace": "rakuten",
        "summary": summary,
        "timeline": {
            date: {
                "sales": round(day["sales"], 2),
                "orders": round(day["orders"], 2),
                "adCost": round(day["adCost"], 2),
            }
            for date, day in timeline.items()
        },
        "products": list(families.values()),
        "notes": notes,
        "sources": sources,
    }


def build_combined_timeline(amazon: dict[str, Any], rakuten: dict[str, Any]) -> list[dict[str, Any]]:
    dates = sorted(set(amazon["timeline"]) | set(rakuten["timeline"]))
    series = []
    for date in dates:
        amazon_day = amazon["timeline"].get(date, {})
        rakuten_day = rakuten["timeline"].get(date, {})
        amazon_sales = float(amazon_day.get("sales", 0.0))
        rakuten_sales = float(rakuten_day.get("sales", 0.0))
        amazon_orders = float(amazon_day.get("orders", 0.0))
        rakuten_orders = float(rakuten_day.get("orders", 0.0))
        amazon_ad_cost = float(amazon_day.get("adCost", 0.0))
        rakuten_ad_cost = float(rakuten_day.get("adCost", 0.0))
        series.append(
            {
                "date": date,
                "amazonSales": round(amazon_sales, 2),
                "rakutenSales": round(rakuten_sales, 2),
                "totalSales": round(amazon_sales + rakuten_sales, 2),
                "amazonOrders": round(amazon_orders, 2),
                "rakutenOrders": round(rakuten_orders, 2),
                "totalOrders": round(amazon_orders + rakuten_orders, 2),
                "amazonAdCost": round(amazon_ad_cost, 2),
                "rakutenAdCost": round(rakuten_ad_cost, 2),
                "totalAdCost": round(amazon_ad_cost + rakuten_ad_cost, 2),
            }
        )
    return series


def build_dashboard(root: Path) -> dict[str, Any]:
    amazon = build_amazon_marketplace(root)
    rakuten = build_rakuten_marketplace(root)
    all_products = [*amazon["products"], *rakuten["products"]]
    for detail in all_products:
        detail["summary"]["adCost"] = round(detail["summary"].get("adCost", 0) or 0, 2) if detail["summary"].get("adCost") is not None else None
        detail["summary"]["adRatio"] = round_metric(detail["summary"].get("adRatio"))
    timeline = build_combined_timeline(amazon, rakuten)
    total_sales = amazon["summary"]["sales"] + rakuten["summary"]["sales"]
    total_orders = amazon["summary"]["orders"] + rakuten["summary"]["orders"]
    total_units = amazon["summary"]["units"] + rakuten["summary"]["units"]
    available_ad_costs = [
        value for value in (amazon["summary"]["adCost"], rakuten["summary"]["adCost"]) if value is not None
    ]
    total_ad_cost = sum(available_ad_costs)
    overall_summary = {
        "sales": round(total_sales, 2),
        "orders": round(total_orders, 2),
        "units": round(total_units, 2),
        "fees": round(amazon["summary"]["fees"] + rakuten["summary"]["fees"], 2),
        "adCost": round(total_ad_cost, 2) if available_ad_costs else None,
        "adRatio": round_metric(safe_div(total_ad_cost, total_sales)) if available_ad_costs else None,
        "bundleRate": amazon["summary"]["bundleRate"],
        "averageOrderValue": round_metric(safe_div(total_sales, total_orders)),
    }
    all_products.sort(key=lambda detail: (detail["summary"]["sales"], detail["summary"]["units"]), reverse=True)
    product_details = {detail["id"]: detail for detail in all_products}
    products = [summarize_product(detail) for detail in all_products]
    sources = [*amazon["sources"], *rakuten["sources"]]
    notes = [
        *amazon["notes"],
        *rakuten["notes"],
    ]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "overall": overall_summary,
            "amazon": amazon["summary"],
            "rakuten": rakuten["summary"],
        },
        "timeline": timeline,
        "products": products,
        "productDetails": product_details,
        "sources": sources,
        "notes": notes,
    }
