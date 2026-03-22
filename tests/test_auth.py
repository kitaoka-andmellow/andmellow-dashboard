import sys
import types
import unittest
from unittest import mock

from eanalytics import auth


class AuthTest(unittest.TestCase):
    def test_session_round_trip(self) -> None:
        with mock.patch("eanalytics.auth.time.time", return_value=1_700_000_000):
            token, expires_at = auth.create_session("user@andmellow.jp", "sub-1", "andmellow.jp")
        self.assertEqual(expires_at, 1_700_007_200)
        with mock.patch("eanalytics.auth.time.time", return_value=1_700_000_100):
            session = auth.parse_session(token)
        self.assertIsNotNone(session)
        self.assertEqual(session.email, "user@andmellow.jp")
        self.assertEqual(session.hd, "andmellow.jp")

    def test_expired_session_is_rejected(self) -> None:
        with mock.patch("eanalytics.auth.time.time", return_value=100):
            token, _ = auth.create_session("user@andmellow.jp", "sub-1", "andmellow.jp")
        with mock.patch("eanalytics.auth.time.time", return_value=100 + auth.SESSION_TTL_SECONDS + 1):
            self.assertIsNone(auth.parse_session(token))

    def test_verify_google_credential_checks_domain(self) -> None:
        request_module = types.ModuleType("google.auth.transport.requests")
        request_module.Request = object

        id_token_module = types.ModuleType("google.oauth2.id_token")

        def fake_verify(_credential, _request, _audience):
            return {
                "iss": "https://accounts.google.com",
                "email": "member@andmellow.jp",
                "email_verified": True,
                "hd": "andmellow.jp",
                "sub": "abc123",
            }

        id_token_module.verify_oauth2_token = fake_verify

        modules = {
            "google": types.ModuleType("google"),
            "google.auth": types.ModuleType("google.auth"),
            "google.auth.transport": types.ModuleType("google.auth.transport"),
            "google.auth.transport.requests": request_module,
            "google.oauth2": types.ModuleType("google.oauth2"),
            "google.oauth2.id_token": id_token_module,
        }

        with mock.patch.dict(sys.modules, modules, clear=False):
            with mock.patch.object(auth, "GOOGLE_CLIENT_ID", "client-id"):
                with mock.patch.object(auth, "ALLOWED_EMAIL_DOMAIN", "andmellow.jp"):
                    payload = auth.verify_google_credential("token")
        self.assertEqual(payload["email"], "member@andmellow.jp")

    def test_verify_google_credential_rejects_wrong_domain(self) -> None:
        request_module = types.ModuleType("google.auth.transport.requests")
        request_module.Request = object

        id_token_module = types.ModuleType("google.oauth2.id_token")

        def fake_verify(_credential, _request, _audience):
            return {
                "iss": "https://accounts.google.com",
                "email": "member@example.com",
                "email_verified": True,
                "hd": "example.com",
                "sub": "abc123",
            }

        id_token_module.verify_oauth2_token = fake_verify

        modules = {
            "google": types.ModuleType("google"),
            "google.auth": types.ModuleType("google.auth"),
            "google.auth.transport": types.ModuleType("google.auth.transport"),
            "google.auth.transport.requests": request_module,
            "google.oauth2": types.ModuleType("google.oauth2"),
            "google.oauth2.id_token": id_token_module,
        }

        with mock.patch.dict(sys.modules, modules, clear=False):
            with mock.patch.object(auth, "GOOGLE_CLIENT_ID", "client-id"):
                with mock.patch.object(auth, "ALLOWED_EMAIL_DOMAIN", "andmellow.jp"):
                    with self.assertRaises(auth.AuthError):
                        auth.verify_google_credential("token")


if __name__ == "__main__":
    unittest.main()
