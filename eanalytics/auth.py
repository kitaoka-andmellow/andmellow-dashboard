from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "ecanalytics_session")
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "7200"))
ALLOWED_EMAIL_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "andmellow.jp").lower()
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-change-me").encode("utf-8")
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "1") != "0"


class AuthError(Exception):
    pass


@dataclass
class SessionData:
    email: str
    sub: str
    exp: int
    hd: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "email": self.email,
            "sub": self.sub,
            "exp": self.exp,
            "hd": self.hd,
        }


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(value: str) -> str:
    digest = hmac.new(SESSION_SECRET, value.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_session(email: str, sub: str, hosted_domain: str | None = None) -> tuple[str, int]:
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = SessionData(
        email=email.lower(),
        sub=sub,
        exp=expires_at,
        hd=hosted_domain.lower() if hosted_domain else None,
    )
    encoded = _b64encode(json.dumps(payload.to_dict(), separators=(",", ":")).encode("utf-8"))
    signature = _sign(encoded)
    return f"{encoded}.{signature}", expires_at


def parse_session(cookie_value: str | None) -> SessionData | None:
    if not cookie_value:
        return None
    try:
        encoded, signature = cookie_value.split(".", 1)
    except ValueError:
        return None
    expected = _sign(encoded)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64decode(encoded).decode("utf-8"))
        session = SessionData(
            email=str(payload["email"]).lower(),
            sub=str(payload["sub"]),
            exp=int(payload["exp"]),
            hd=str(payload["hd"]).lower() if payload.get("hd") else None,
        )
    except (KeyError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if session.exp <= int(time.time()):
        return None
    return session


def verify_google_credential(credential: str) -> dict[str, Any]:
    if not GOOGLE_CLIENT_ID:
        raise AuthError("GOOGLE_CLIENT_ID is not configured.")
    if not credential:
        raise AuthError("Missing Google credential.")

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token
    except ImportError as exc:
        raise AuthError("Google auth libraries are not installed.") from exc

    try:
        payload = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as exc:  # pragma: no cover - exact exception depends on google-auth internals
        raise AuthError("Failed to verify Google credential.") from exc

    issuer = payload.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise AuthError("Invalid token issuer.")

    email = str(payload.get("email", "")).lower()
    hosted_domain = str(payload.get("hd", "")).lower()
    email_verified = bool(payload.get("email_verified"))
    if not email_verified:
        raise AuthError("Google account email is not verified.")
    if hosted_domain != ALLOWED_EMAIL_DOMAIN or not email.endswith(f"@{ALLOWED_EMAIL_DOMAIN}"):
        raise AuthError(f"Only @{ALLOWED_EMAIL_DOMAIN} accounts are allowed.")

    return {
        "email": email,
        "sub": str(payload.get("sub", "")),
        "hd": hosted_domain,
    }


def session_cookie_value(token: str, expires_at: int, secure: bool) -> str:
    parts = [
        f"{SESSION_COOKIE_NAME}={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={max(0, expires_at - int(time.time()))}",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def expired_session_cookie_value(secure: bool) -> str:
    parts = [
        f"{SESSION_COOKIE_NAME}=",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        "Max-Age=0",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def auth_config() -> dict[str, Any]:
    return {
        "required": AUTH_REQUIRED,
        "googleClientId": GOOGLE_CLIENT_ID,
        "allowedDomain": ALLOWED_EMAIL_DOMAIN,
        "sessionTtlSeconds": SESSION_TTL_SECONDS,
    }


def secure_cookies_enabled() -> bool:
    forced = os.environ.get("COOKIE_SECURE")
    if forced is not None:
        return forced not in {"0", "false", "False"}
    return bool(os.environ.get("K_SERVICE"))
