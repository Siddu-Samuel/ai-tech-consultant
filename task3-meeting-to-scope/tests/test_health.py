import unittest

from fastapi.testclient import TestClient

from app.main import app


class HealthTests(unittest.TestCase):
    def test_health_reports_demo_or_live_mode(self) -> None:
        response = TestClient(app).get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "meeting-to-scope")
        self.assertIn(body["mode"], {"demo", "live"})
