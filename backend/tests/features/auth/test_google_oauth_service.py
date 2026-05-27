import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app.features.auth.google_oauth_service import GoogleOAuthService


class GoogleOAuthServiceTests(unittest.TestCase):
    def test_loads_web_client_config_from_json_file(self) -> None:
        path = Path(__file__).resolve().parent / "_client_secret_test.json"
        try:
            path.write_text(
                json.dumps(
                    {
                        "web": {
                            "client_id": "client-id.apps.googleusercontent.com",
                            "client_secret": "secret-value",
                            "redirect_uris": ["http://localhost:8000/auth/callback"],
                            "javascript_origins": ["http://localhost:8000"],
                        }
                    }
                ),
                encoding="utf-8",
            )

            service = GoogleOAuthService(
                client_id="",
                client_secret="",
                redirect_uris=(),
                javascript_origins=(),
                client_json_path=str(path),
                allowed_domains=("example.com", "example.com"),
            )
        finally:
            path.unlink(missing_ok=True)

        self.assertTrue(service.is_configured)
        self.assertEqual(service.client_id, "client-id.apps.googleusercontent.com")
        self.assertEqual(service.redirect_uris, ["http://localhost:8000/auth/callback"])

    def test_allows_only_configured_surveysense_domains(self) -> None:
        service = GoogleOAuthService(
            client_id="",
            client_secret="",
            redirect_uris=(),
            javascript_origins=(),
            client_json_path="",
            allowed_domains=("example.com", "example.com"),
        )

        self.assertTrue(service.is_allowed_email("person@example.com"))
        self.assertTrue(service.is_allowed_email("person@example.com"))
        self.assertFalse(service.is_allowed_email("person@gmail.com"))
        self.assertFalse(service.is_allowed_email("person@surveysense.org"))

    def test_loads_client_config_from_env_values(self) -> None:
        service = GoogleOAuthService(
            client_id="client-id.apps.googleusercontent.com",
            client_secret="secret-value",
            redirect_uris=("https://verbatimapp.onrender.com/auth/callback",),
            javascript_origins=("https://verbatimapp.onrender.com",),
            client_json_path="",
            allowed_domains=("example.com", "example.com"),
        )

        self.assertTrue(service.is_configured)
        self.assertEqual(service.client_id, "client-id.apps.googleusercontent.com")
        self.assertEqual(service.redirect_uris, ["https://verbatimapp.onrender.com/auth/callback"])

    def test_verify_credential_allows_small_clock_skew(self) -> None:
        service = GoogleOAuthService(
            client_id="client-id.apps.googleusercontent.com",
            client_secret="secret-value",
            redirect_uris=("https://verbatimapp.onrender.com/auth/callback",),
            javascript_origins=("https://verbatimapp.onrender.com",),
            client_json_path="",
            allowed_domains=("example.com", "example.com"),
        )

        with patch("app.features.auth.google_oauth_service.GoogleRequest", return_value=object()), patch(
            "app.features.auth.google_oauth_service.id_token"
        ) as mock_id_token:
            mock_id_token.verify_oauth2_token.return_value = {
                "email": "person@example.com",
                "email_verified": True,
                "name": "Person Example",
                "picture": "https://example.com/avatar.png",
            }

            user = service.verify_credential("test-credential")

        mock_id_token.verify_oauth2_token.assert_called_once_with(
            "test-credential",
            unittest.mock.ANY,
            "client-id.apps.googleusercontent.com",
            clock_skew_in_seconds=30,
        )
        self.assertEqual(user.email, "person@example.com")
        self.assertEqual(user.name, "Person Example")
        self.assertEqual(user.picture, "https://example.com/avatar.png")

    def test_verify_credential_uses_configured_domains_in_error_message(self) -> None:
        service = GoogleOAuthService(
            client_id="client-id.apps.googleusercontent.com",
            client_secret="secret-value",
            redirect_uris=("https://verbatimapp.onrender.com/auth/callback",),
            javascript_origins=("https://verbatimapp.onrender.com",),
            client_json_path="",
            allowed_domains=("example.com",),
        )

        with patch("app.features.auth.google_oauth_service.GoogleRequest", return_value=object()), patch(
            "app.features.auth.google_oauth_service.id_token"
        ) as mock_id_token:
            mock_id_token.verify_oauth2_token.return_value = {
                "email": "person@other.com",
                "email_verified": True,
            }

            with self.assertRaises(PermissionError) as exc:
                service.verify_credential("test-credential")

        self.assertEqual(str(exc.exception), "Only @example.com accounts are allowed.")


if __name__ == "__main__":
    unittest.main()
