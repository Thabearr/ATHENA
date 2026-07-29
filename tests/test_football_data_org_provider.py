import json
import unittest
from unittest.mock import Mock, call, patch

from api.football_data_org_provider import FootballDataOrgProvider


class FootballDataOrgProviderPortabilityTests(unittest.TestCase):
    API_KEY = "mock-api-key-value"

    def test_windows_curl_exe_resolution(self):
        windows_curl = r"C:\Windows\System32\curl.exe"

        with patch(
            "api.curl_json_client.shutil.which",
            side_effect=lambda candidate: (
                windows_curl if candidate == "curl.exe" else None
            ),
        ) as which:
            provider = FootballDataOrgProvider(self.API_KEY)

        self.assertEqual(provider.curl_executable, windows_curl)
        self.assertEqual(
            which.call_args_list,
            [call("curl"), call("curl.exe")],
        )

    def test_linux_curl_resolution(self):
        linux_curl = "/usr/local/bin/curl"

        with patch(
            "api.curl_json_client.shutil.which",
            return_value=linux_curl,
        ) as which:
            provider = FootballDataOrgProvider(self.API_KEY)

        self.assertEqual(provider.curl_executable, linux_curl)
        which.assert_called_once_with("curl")

    def test_missing_curl_raises_safe_clear_error(self):
        with patch(
            "api.curl_json_client.shutil.which",
            return_value=None,
        ), patch(
            "api.curl_json_client.subprocess.run"
        ) as run:
            with self.assertRaises(RuntimeError) as captured:
                FootballDataOrgProvider(self.API_KEY)

        message = str(captured.exception)
        self.assertIn("curl executable could not be found", message)
        self.assertNotIn(self.API_KEY, message)
        run.assert_not_called()

    def test_resolved_executable_and_auth_header_are_passed_safely(self):
        resolved_curl = r"C:\Tools\curl.exe"
        completed = Mock(
            returncode=0,
            stdout=json.dumps({"competitions": []}).encode("utf-8"),
            stderr=b"",
        )

        with patch(
            "api.curl_json_client.shutil.which",
            return_value=resolved_curl,
        ), patch(
            "api.curl_json_client.subprocess.run",
            return_value=completed,
        ) as run:
            provider = FootballDataOrgProvider(self.API_KEY)
            provider.get_available_competitions()

        command = run.call_args.args[0]
        self.assertEqual(command[0], resolved_curl)
        self.assertEqual(
            command[command.index("--header") + 1],
            f"X-Auth-Token: {self.API_KEY}",
        )
        self.assertEqual(
            sum(self.API_KEY in argument for argument in command),
            1,
        )
        self.assertIn("--http1.1", command)
        self.assertEqual(
            command[command.index("--connect-timeout") + 1],
            "20",
        )
        self.assertEqual(
            command[command.index("--max-time") + 1],
            "60",
        )
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_rate_limit_retry_and_json_parsing_are_preserved(self):
        rate_limited = json.dumps(
            {
                "errorCode": 429,
                "message": "Wait 2 seconds before retrying",
            }
        )
        successful = json.dumps(
            {
                "matches": [
                    {
                        "id": 42,
                        "score": {
                            "fullTime": {"home": 2, "away": 1},
                        },
                    }
                ]
            }
        )

        with patch(
            "api.curl_json_client.shutil.which",
            return_value="/mock/curl",
        ), patch(
            "api.curl_json_client.subprocess.run"
        ) as run:
            provider = FootballDataOrgProvider(self.API_KEY)

        with patch.object(
            provider,
            "_single_curl_attempt",
            side_effect=[
                json.loads(rate_limited),
                json.loads(successful),
            ],
        ) as attempt, patch(
            "api.football_data_org_provider.time.sleep"
        ) as sleep:
            matches = provider.get_matches("TEST", status="FINISHED")

        self.assertEqual(matches, json.loads(successful)["matches"])
        self.assertEqual(attempt.call_count, 2)
        sleep.assert_called_once_with(3)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
