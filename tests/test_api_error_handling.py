import unittest

from fastapi.testclient import TestClient

from api.server import app


class ApiErrorHandlingTests(unittest.TestCase):
    def test_legacy_generate_is_blocked_without_execution(self):
        client = TestClient(app)
        response = client.post("/api/generate", json={"days": 1, "folds": 1, "strict": True})
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["code"], "LEGACY_GENERATE_BLOCKED")
        self.assertEqual(response.json()["replacement"], "/api/v1/run-previews")
        self.assertIn("unsupported", response.json()["message"])


if __name__ == "__main__":
    unittest.main()
