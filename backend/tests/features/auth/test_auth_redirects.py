import unittest
from unittest.mock import patch

from app.core.settings import Settings
from app.main import create_app
from fastapi.testclient import TestClient


class AuthRedirectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_root_serves_public_landing_page(self) -> None:
        response = self.client.get(
            "/",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("SurveySense", response.text)

    def test_app_redirects_to_login_when_not_authenticated(self) -> None:
        response = self.client.get(
            "/app",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/login")

    def test_unknown_page_loads_do_not_redirect_to_login(self) -> None:
        response = self.client.get(
            "/results",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(response.headers.get("location"))

    def test_api_request_stays_unauthorized_instead_of_html_redirect(self) -> None:
        response = self.client.get(
            "/result-rows/example?dataset=transformed&offset=0&limit=10",
            headers={"accept": "application/json"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 401)

    def test_crawl_files_are_public(self) -> None:
        robots_response = self.client.get("/robots.txt", follow_redirects=False)
        sitemap_response = self.client.get("/sitemap.xml", follow_redirects=False)

        self.assertEqual(robots_response.status_code, 200)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", robots_response.text)
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertIn("<loc>http://testserver/</loc>", sitemap_response.text)
        self.assertNotIn("<loc>http://testserver/login</loc>", sitemap_response.text)

    def test_create_app_rejects_missing_session_secret(self) -> None:
        production_settings = Settings(app_env="production", session_secret="")

        with patch("app.main.get_settings", return_value=production_settings):
            with self.assertRaises(RuntimeError):
                create_app()


if __name__ == "__main__":
    unittest.main()
