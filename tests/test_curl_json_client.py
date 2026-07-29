import json
import unittest
from unittest.mock import Mock, patch

from api.curl_json_client import (
    MAX_DIAGNOSTIC_EXCERPT,
    CurlJsonClient,
)


class CurlJsonClientTests(unittest.TestCase):
    API_KEY = "transport-mock-secret"

    @staticmethod
    def _result(*, returncode=0, stdout=b"", stderr=b""):
        return Mock(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_utf8_json_is_decoded_independently_of_windows_locale(self):
        payload = {
            "teams": [
                "Malmö FF",
                "Legia Warszawa",
                "北京国安",
                "São Paulo",
            ]
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        with patch(
            "api.curl_json_client.shutil.which",
            return_value=r"C:\Windows\System32\curl.exe",
        ), patch(
            "api.curl_json_client.subprocess.run",
            return_value=self._result(stdout=encoded),
        ), patch(
            "locale.getpreferredencoding",
            return_value="cp1252",
        ):
            result = CurlJsonClient().request_json(
                "https://provider.invalid/teams",
                headers={"X-Auth-Token": self.API_KEY},
            )

        self.assertEqual(result, payload)

    def test_missing_curl_error_is_clear_and_safe(self):
        with patch(
            "api.curl_json_client.shutil.which",
            return_value=None,
        ), patch(
            "api.curl_json_client.subprocess.run"
        ) as run:
            with self.assertRaises(RuntimeError) as captured:
                CurlJsonClient()

        message = str(captured.exception)
        self.assertIn("curl executable could not be found", message)
        self.assertNotIn(self.API_KEY, message)
        run.assert_not_called()

    def test_invalid_json_uses_bounded_redacted_excerpt(self):
        full_response = (
            f'not-json X-Auth-Token: {self.API_KEY} '
            + ("private-provider-payload-" * 80)
        ).encode("utf-8")

        with patch(
            "api.curl_json_client.shutil.which",
            return_value="/mock/curl",
        ), patch(
            "api.curl_json_client.subprocess.run",
            return_value=self._result(stdout=full_response),
        ):
            with self.assertRaises(RuntimeError) as captured:
                CurlJsonClient().request_json(
                    "https://provider.invalid/data",
                    headers={"X-Auth-Token": self.API_KEY},
                )

        message = str(captured.exception)
        self.assertIn("invalid JSON", message)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn(self.API_KEY, message)
        self.assertNotIn(full_response.decode("utf-8"), message)
        self.assertLessEqual(
            len(message),
            MAX_DIAGNOSTIC_EXCERPT + 100,
        )

    def test_non_utf8_stderr_cannot_break_safe_error_reporting(self):
        stderr = (
            b"\xff\xfe curl diagnostic x-apisports-key: "
            + self.API_KEY.encode("utf-8")
        )

        with patch(
            "api.curl_json_client.shutil.which",
            return_value="/mock/curl",
        ), patch(
            "api.curl_json_client.subprocess.run",
            return_value=self._result(
                returncode=7,
                stderr=stderr,
            ),
        ):
            with self.assertRaises(RuntimeError) as captured:
                CurlJsonClient().request_json(
                    "https://provider.invalid/data",
                    headers={"x-apisports-key": self.API_KEY},
                )

        message = str(captured.exception)
        self.assertIn("Curl request failed with exit code 7", message)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn(self.API_KEY, message)


if __name__ == "__main__":
    unittest.main()
