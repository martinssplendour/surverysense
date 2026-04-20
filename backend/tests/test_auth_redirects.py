import unittest
from unittest.mock import patch

from app.core.settings import Settings
from app.main import create_app
from fastapi.testclient import TestClient


class AuthRedirectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_root_redirects_to_login_when_not_authenticated(self) -> None:
        response = self.client.get(
            "/",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/login")

    def test_results_redirects_to_login_when_not_authenticated(self) -> None:
        response = self.client.get(
            "/results",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/login")

    def test_api_request_stays_unauthorized_instead_of_html_redirect(self) -> None:
        response = self.client.get(
            "/result-rows/example?dataset=transformed&offset=0&limit=10",
            headers={"accept": "application/json"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 401)

    def test_create_app_rejects_missing_session_secret(self) -> None:
        production_settings = Settings(app_env="production", session_secret="")

        with patch("app.main.get_settings", return_value=production_settings):
            with self.assertRaises(RuntimeError):
                create_app()


if __name__ == "__main__":
    unittest.main()
