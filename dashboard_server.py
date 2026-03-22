from __future__ import annotations

import json
import mimetypes
import os
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from eanalytics import build_dashboard
from eanalytics.auth import (
    AUTH_REQUIRED,
    SESSION_COOKIE_NAME,
    AuthError,
    auth_config,
    create_session,
    expired_session_cookie_value,
    parse_session,
    secure_cookies_enabled,
    session_cookie_value,
    verify_google_credential,
)

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DATA_ROOT = Path(os.environ.get("DATA_ROOT", str(ROOT))).expanduser().resolve()
STATIC_ROOT_FILES = {"logo.png", "favicon.ico", "amazon-logo.png", "rakuten-logo.png"}


class DashboardHandler(SimpleHTTPRequestHandler):
    def send_json(self, payload: dict, status: int = HTTPStatus.OK, extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        raw = self.rfile.read(content_length) if content_length > 0 else b""
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def current_session(self):
        cookie_header = self.headers.get("Cookie", "")
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        morsel = cookies.get(SESSION_COOKIE_NAME)
        token = morsel.value if morsel else None
        return parse_session(token)

    def require_session(self):
        if not AUTH_REQUIRED:
            return None
        session = self.current_session()
        if session is None:
            self.send_json({"error": "Authentication required."}, HTTPStatus.UNAUTHORIZED)
            return None
        return session

    def translate_path(self, path: str) -> str:
        cleaned = path.split("?", 1)[0].split("#", 1)[0]
        if cleaned in {"/", ""}:
            return str(WEB_ROOT / "index.html")
        relative = cleaned.lstrip("/")
        project_path = ROOT / relative
        if relative in STATIC_ROOT_FILES and project_path.exists():
            return str(project_path)
        return str(WEB_ROOT / relative)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route == "/healthz":
            body = b"ok"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "/api/auth/config":
            self.send_json(auth_config())
            return
        if route == "/api/session":
            session = self.current_session()
            self.send_json(
                {
                    "authenticated": bool(session) or not AUTH_REQUIRED,
                    "email": session.email if session else None,
                    "expiresAt": session.exp if session else None,
                    "required": AUTH_REQUIRED,
                },
            )
            return
        if route == "/api/dashboard":
            session = self.require_session()
            if AUTH_REQUIRED and session is None:
                return
            period_start = query.get("start", [None])[0]
            period_end = query.get("end", [None])[0]
            payload = build_dashboard(DATA_ROOT, period_start=period_start, period_end=period_end)
            self.send_json(payload)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0]
        if route == "/api/auth/google":
            try:
                payload = self.read_json_body()
                verified = verify_google_credential(str(payload.get("credential", "")))
                token, expires_at = create_session(
                    verified["email"],
                    verified["sub"],
                    verified.get("hd"),
                )
                self.send_json(
                    {
                        "authenticated": True,
                        "email": verified["email"],
                        "expiresAt": expires_at,
                    },
                    extra_headers={
                        "Set-Cookie": session_cookie_value(token, expires_at, secure_cookies_enabled()),
                    },
                )
            except AuthError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.UNAUTHORIZED)
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON body."}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/logout":
            self.send_json(
                {"authenticated": False},
                extra_headers={"Set-Cookie": expired_session_cookie_value(secure_cookies_enabled())},
            )
            return
        self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def guess_type(self, path: str) -> str:
        guessed = mimetypes.guess_type(path)[0]
        return guessed or "application/octet-stream"


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard server running at http://{host}:{port} using data root {DATA_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
