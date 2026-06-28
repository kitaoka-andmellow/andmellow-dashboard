"""Amazon review request batch for Seller Central orders.

This script uses Amazon Selling Partner API directly:
- Orders API: list shipped orders in a configurable age window.
- Solicitations API: check eligible solicitation actions per order.
- Solicitations API: request product review + seller feedback only when eligible.

No order IDs are committed back to the repository. Amazon's solicitation action
availability is used as the source of truth to avoid duplicate requests.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import requests
from requests import Response
from requests_aws4auth import AWS4Auth


REGION_CONFIG = {
    "NA": {
        "endpoint": "https://sellingpartnerapi-na.amazon.com",
        "aws_region": "us-east-1",
    },
    "EU": {
        "endpoint": "https://sellingpartnerapi-eu.amazon.com",
        "aws_region": "eu-west-1",
    },
    "FE": {
        "endpoint": "https://sellingpartnerapi-fe.amazon.com",
        "aws_region": "us-west-2",
    },
}

REQUIRED_ENV = [
    "LWA_CLIENT_ID",
    "LWA_CLIENT_SECRET",
    "LWA_REFRESH_TOKEN",
    "MARKETPLACE_ID",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
]


@dataclass(frozen=True)
class Settings:
    marketplace_id: str
    sp_api_region: str
    endpoint: str
    aws_region: str
    lookback_days: int
    min_age_days: int
    max_requests_per_run: int
    dry_run: bool
    skip_if_missing_secrets: bool


def getenv_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings() -> Settings:
    sp_api_region = os.getenv("SP_API_REGION", "FE").upper()
    if sp_api_region not in REGION_CONFIG:
        raise ValueError("SP_API_REGION must be one of: NA, EU, FE")

    return Settings(
        marketplace_id=os.getenv("MARKETPLACE_ID", "").strip(),
        sp_api_region=sp_api_region,
        endpoint=os.getenv("SP_API_ENDPOINT", REGION_CONFIG[sp_api_region]["endpoint"]).rstrip("/"),
        aws_region=os.getenv("SP_API_AWS_REGION", REGION_CONFIG[sp_api_region]["aws_region"]),
        lookback_days=int(os.getenv("ORDER_LOOKBACK_DAYS", "30")),
        min_age_days=int(os.getenv("ORDER_MIN_AGE_DAYS", "5")),
        max_requests_per_run=int(os.getenv("MAX_REQUESTS_PER_RUN", "200")),
        dry_run=getenv_bool("DRY_RUN", default=True),
        skip_if_missing_secrets=getenv_bool("SKIP_IF_MISSING_SECRETS", default=True),
    )


def validate_environment(settings: Settings) -> bool:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if not settings.marketplace_id and "MARKETPLACE_ID" not in missing:
        missing.append("MARKETPLACE_ID")

    if not missing:
        return True

    message = "Missing required environment variables: " + ", ".join(sorted(set(missing)))
    if settings.skip_if_missing_secrets:
        print(f"{message}. Skipping run because SKIP_IF_MISSING_SECRETS=true.")
        return False

    raise RuntimeError(message)


def get_lwa_access_token() -> str:
    response = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ["LWA_REFRESH_TOKEN"],
            "client_id": os.environ["LWA_CLIENT_ID"],
            "client_secret": os.environ["LWA_CLIENT_SECRET"],
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("LWA token response did not include access_token")
    return token


def build_auth(settings: Settings) -> AWS4Auth:
    access_key = os.environ["AWS_ACCESS_KEY_ID"]
    secret_key = os.environ["AWS_SECRET_ACCESS_KEY"]
    session_token = os.getenv("AWS_SESSION_TOKEN")

    role_arn = os.getenv("AWS_ROLE_ARN")
    if role_arn:
        sts = boto3.client(
            "sts",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            region_name=settings.aws_region,
        )
        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="amazon-review-request-batch",
        )["Credentials"]
        access_key = assumed["AccessKeyId"]
        secret_key = assumed["SecretAccessKey"]
        session_token = assumed["SessionToken"]

    return AWS4Auth(
        access_key,
        secret_key,
        settings.aws_region,
        "execute-api",
        session_token=session_token,
    )


def request_sp_api(
    method: str,
    path: str,
    *,
    settings: Settings,
    lwa_token: str,
    auth: AWS4Auth,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{settings.endpoint}{path}"
    headers = {
        "x-amz-access-token": lwa_token,
        "user-agent": "andmellow-review-request-batch/1.0",
        "accept": "application/json",
    }

    if json_body is not None:
        headers["content-type"] = "application/json"

    for attempt in range(5):
        response: Response = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=headers,
            auth=auth,
            timeout=60,
        )

        if response.status_code in {429, 500, 502, 503, 504}:
            sleep_seconds = min(2**attempt, 30)
            print(
                f"Retryable SP-API response {response.status_code} for {method} {path}. "
                f"Sleeping {sleep_seconds}s."
            )
            time.sleep(sleep_seconds)
            continue

        if response.status_code >= 400:
            body = response.text[:1000]
            raise RuntimeError(f"SP-API error {response.status_code} for {method} {path}: {body}")

        if response.status_code == 204 or not response.text:
            return {}

        return response.json()

    raise RuntimeError(f"SP-API request failed after retries: {method} {path}")


def iter_orders(settings: Settings, lwa_token: str, auth: AWS4Auth) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    created_after = (now - timedelta(days=settings.lookback_days)).isoformat().replace("+00:00", "Z")
    created_before = (now - timedelta(days=settings.min_age_days)).isoformat().replace("+00:00", "Z")

    orders: list[dict[str, Any]] = []
    next_token: str | None = None

    while True:
        if next_token:
            params = {"NextToken": next_token}
        else:
            params = {
                "MarketplaceIds": settings.marketplace_id,
                "CreatedAfter": created_after,
                "CreatedBefore": created_before,
                "OrderStatuses": "Shipped",
            }

        payload = request_sp_api(
            "GET",
            "/orders/v0/orders",
            settings=settings,
            lwa_token=lwa_token,
            auth=auth,
            params=params,
        ).get("payload", {})

        batch = payload.get("Orders", [])
        orders.extend(batch)
        print(f"Fetched {len(batch)} orders. Total fetched: {len(orders)}")

        next_token = payload.get("NextToken")
        if not next_token:
            break

        time.sleep(1.2)

    return orders


def is_review_request_available(actions_payload: dict[str, Any]) -> bool:
    payload = actions_payload.get("payload", actions_payload)
    actions = payload.get("actions") or payload.get("Actions") or []

    for action in actions:
        name = str(action.get("name") or action.get("Name") or "").lower()
        normalized = name.replace("-", "").replace("_", "")
        if "productreviewandsellerfeedback" in normalized:
            return True

    return False


def get_available_actions(
    order_id: str,
    *,
    settings: Settings,
    lwa_token: str,
    auth: AWS4Auth,
) -> dict[str, Any]:
    return request_sp_api(
        "GET",
        f"/solicitations/v1/orders/{order_id}",
        settings=settings,
        lwa_token=lwa_token,
        auth=auth,
        params={"marketplaceIds": settings.marketplace_id},
    )


def create_review_request(
    order_id: str,
    *,
    settings: Settings,
    lwa_token: str,
    auth: AWS4Auth,
) -> None:
    request_sp_api(
        "POST",
        f"/solicitations/v1/orders/{order_id}/solicitations/productReviewAndSellerFeedback",
        settings=settings,
        lwa_token=lwa_token,
        auth=auth,
        params={"marketplaceIds": settings.marketplace_id},
        json_body={},
    )


def main() -> int:
    settings = load_settings()
    if not validate_environment(settings):
        return 0

    if settings.min_age_days >= settings.lookback_days:
        raise ValueError("ORDER_MIN_AGE_DAYS must be smaller than ORDER_LOOKBACK_DAYS")

    print(
        "Starting Amazon review request batch: "
        f"region={settings.sp_api_region}, marketplace={settings.marketplace_id}, "
        f"window={settings.lookback_days}d_to_{settings.min_age_days}d, "
        f"max_requests={settings.max_requests_per_run}, dry_run={settings.dry_run}"
    )

    lwa_token = get_lwa_access_token()
    auth = build_auth(settings)
    orders = iter_orders(settings, lwa_token, auth)

    sent_count = 0
    eligible_count = 0
    skipped_count = 0
    failed_count = 0

    for order in orders:
        order_id = order.get("AmazonOrderId")
        if not order_id:
            skipped_count += 1
            continue

        try:
            actions = get_available_actions(order_id, settings=settings, lwa_token=lwa_token, auth=auth)
            if not is_review_request_available(actions):
                skipped_count += 1
                print(f"skip_not_available: {order_id}")
                time.sleep(1.2)
                continue

            eligible_count += 1

            if settings.dry_run:
                print(f"dry_run_available: {order_id}")
            else:
                create_review_request(order_id, settings=settings, lwa_token=lwa_token, auth=auth)
                sent_count += 1
                print(f"sent: {order_id}")

            if eligible_count >= settings.max_requests_per_run:
                print("Reached MAX_REQUESTS_PER_RUN. Stopping.")
                break

            time.sleep(1.2)

        except Exception as exc:  # Keep batch moving, but surface failure details.
            failed_count += 1
            print(f"failed: {order_id}: {exc}")
            time.sleep(1.2)

    print(
        "Batch finished: "
        f"orders={len(orders)}, eligible={eligible_count}, sent={sent_count}, "
        f"skipped={skipped_count}, failed={failed_count}, dry_run={settings.dry_run}"
    )

    if failed_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
