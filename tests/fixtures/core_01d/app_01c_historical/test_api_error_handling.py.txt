import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app


class ApiErrorHandlingTests(unittest.TestCase):
    def test_generate_propagates_400_for_expected_builder_failures(self):
        with patch("api.server.AccaBuilder") as mock_builder:
            mock_builder.return_value.build.return_value = {
                "success": False,
                "error": "No fixtures found in next 1 day(s)",
            }
            client = TestClient(app)
            response = client.post("/api/generate", json={"days": 1, "folds": 1, "strict": True})
            self.assertEqual(response.status_code, 400)
            self.assertIn("No fixtures found", response.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
