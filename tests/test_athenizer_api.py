import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app


class AthenizerApiTests(unittest.TestCase):
    def test_vet_returns_400_for_expected_resolution_failures(self):
        with patch("api.athenizer.betting_svc.vet_code") as mock_vet:
            mock_vet.return_value = {"success": False, "error": "Not supported"}
            client = TestClient(app)
            response = client.post("/api/athenizer/vet", json={"bookmaker": "betway", "booking_code": "ABC123"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "Not supported")

    def test_merge_requires_multiple_codes(self):
        client = TestClient(app)
        response = client.post("/api/athenizer/merge", json={"bookmaker": "sportybet", "booking_codes": ["ONLYONE"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least two", response.json()["detail"])

    def test_merge_merges_unique_legs(self):
        with patch("api.athenizer.betting_svc.vet_code") as mock_vet:
            mock_vet.side_effect = [
                {
                    "success": True,
                    "bookmaker": "SportyBet",
                    "legs": [
                        {"fixture": "Arsenal vs Chelsea", "market": "1X2", "selection": "1", "odds": 1.95}
                    ],
                },
                {
                    "success": True,
                    "bookmaker": "SportyBet",
                    "legs": [
                        {"fixture": "Arsenal vs Chelsea", "market": "1X2", "selection": "1", "odds": 1.95},
                        {"fixture": "Milan vs Roma", "market": "Over 2.5", "selection": "Over", "odds": 1.7},
                    ],
                },
            ]
            client = TestClient(app)
            response = client.post(
                "/api/athenizer/merge",
                json={"bookmaker": "sportybet", "booking_codes": ["A1", "A2"]},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["success"])
            self.assertEqual(payload["codes_merged"], 2)
            self.assertEqual(len(payload["legs"]), 2)
            self.assertAlmostEqual(payload["total_estimated_odds"], 3.31, places=2)


if __name__ == "__main__":
    unittest.main()
