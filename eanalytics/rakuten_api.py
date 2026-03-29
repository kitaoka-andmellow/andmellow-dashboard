from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import requests

JST = timezone(timedelta(hours=9))
SEARCH_ORDER_URL = "https://api.rms.rakuten.co.jp/es/2.0/order/searchOrder/"
GET_ORDER_URL = "https://api.rms.rakuten.co.jp/es/2.0/order/getOrder/"
PAGE_SIZE = 1000
DETAIL_BATCH_SIZE = 100
CHUNK_DAYS = 30
CACHE_TTL_SECONDS = 300

_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}


class RakutenApiError(Exception):
    pass


@dataclass
class RakutenApiCredentials:
    service_secret: str
    license_key: str


def get_rakuten_api_credentials() -> RakutenApiCredentials | None:
    service_secret = (
        os.environ.get("RAKUTEN_SERVICE_SECRET")
        or os.environ.get("RAKUTEN_SERVICESECRET")
        or os.environ.get("RAKUTEN_API_SERVICE_SECRET")
    )
    license_key = (
        os.environ.get("RAKUTEN_LICENSE_KEY")
        or os.environ.get("RAKUTEN_LICENSEKEY")
        or os.environ.get("RAKUTEN_API_LICENSE_KEY")
    )
    if not service_secret or not license_key:
        return None
    return RakutenApiCredentials(service_secret=service_secret, license_key=license_key)


def rakuten_api_enabled() -> bool:
    return get_rakuten_api_credentials() is not None


def _authorization_header(credentials: RakutenApiCredentials) -> str:
    token = f"{credentials.service_secret}:{credentials.license_key}".encode("utf-8")
    # RMS examples use base64 without trailing "=" padding.
    return "ESA " + base64.b64encode(token).decode("ascii").rstrip("=")


def _to_rakuten_datetime(value: str, end_of_day: bool = False) -> str:
    base = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        base = base.replace(hour=23, minute=59, second=59)
    return base.replace(tzinfo=JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def _chunk_periods(period_start: str, period_end: str) -> Iterable[tuple[str, str]]:
    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)
    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS - 1), end_date)
        yield cursor.isoformat(), chunk_end.isoformat()
        cursor = chunk_end + timedelta(days=1)


class RakutenOrderClient:
    def __init__(self, credentials: RakutenApiCredentials, session: requests.Session | None = None) -> None:
        self.credentials = credentials
        self.session = session or requests.Session()

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            url,
            json=payload,
            headers={
                "Authorization": _authorization_header(self.credentials),
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        messages = data.get("MessageModelList") or []
        errors = [item for item in messages if str(item.get("messageType", "")).upper() == "ERROR"]
        if errors:
            detail = "; ".join(str(item.get("message", "")).strip() for item in errors if item.get("message"))
            raise RakutenApiError(detail or "Rakuten API returned an error response.")
        return data

    def search_order_numbers(self, period_start: str, period_end: str) -> list[str]:
        numbers: list[str] = []
        seen: set[str] = set()
        for chunk_start, chunk_end in _chunk_periods(period_start, period_end):
            page = 1
            total_pages = 1
            while page <= total_pages:
                payload = {
                    "dateType": 1,
                    "startDatetime": _to_rakuten_datetime(chunk_start),
                    "endDatetime": _to_rakuten_datetime(chunk_end, end_of_day=True),
                    "PaginationRequestModel": {
                        "requestRecordsAmount": PAGE_SIZE,
                        "requestPage": page,
                    },
                }
                data = self._post(SEARCH_ORDER_URL, payload)
                for number in data.get("orderNumberList") or []:
                    if number and number not in seen:
                        seen.add(number)
                        numbers.append(str(number))
                pagination = data.get("PaginationResponseModel") or {}
                total_pages = int(pagination.get("totalPages") or 1)
                page += 1
        return numbers

    def get_orders(self, order_numbers: list[str]) -> list[dict[str, Any]]:
        orders: list[dict[str, Any]] = []
        for index in range(0, len(order_numbers), DETAIL_BATCH_SIZE):
            batch = order_numbers[index : index + DETAIL_BATCH_SIZE]
            if not batch:
                continue
            payload = {
                "version": 7,
                "orderNumberList": batch,
            }
            data = self._post(GET_ORDER_URL, payload)
            orders.extend(data.get("OrderModelList") or [])
        return orders


def fetch_rakuten_orders(period_start: str, period_end: str) -> list[dict[str, Any]]:
    credentials = get_rakuten_api_credentials()
    if credentials is None:
        return []

    cache_key = (period_start, period_end)
    cached = _CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    client = RakutenOrderClient(credentials)
    order_numbers = client.search_order_numbers(period_start, period_end)
    orders = client.get_orders(order_numbers) if order_numbers else []
    _CACHE[cache_key] = (now, orders)
    return orders
