import json
import unittest
from pathlib import Path

from app.services.google_oauth_service import GoogleOAuthService


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
                client_json_path=str(path),
                allowed_domains=("twinkl.co.uk", "twinkl.com"),
            )
        finally:
            path.unlink(missing_ok=True)

        self.assertTrue(service.is_configured)
        self.assertEqual(service.client_id, "client-id.apps.googleusercontent.com")
        self.assertEqual(service.redirect_uris, ["http://localhost:8000/auth/callback"])

    def test_allows_only_configured_twinkl_domains(self) -> None:
        service = GoogleOAuthService(
            client_json_path="",
            allowed_domains=("twinkl.co.uk", "twinkl.com"),
        )

        self.assertTrue(service.is_allowed_email("person@twinkl.co.uk"))
        self.assertTrue(service.is_allowed_email("person@twinkl.com"))
        self.assertFalse(service.is_allowed_email("person@gmail.com"))
        self.assertFalse(service.is_allowed_email("person@twinkl.org"))


if __name__ == "__main__":
    unittest.main()
