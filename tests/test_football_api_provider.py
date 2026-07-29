import json
import unittest
from unittest.mock import Mock, call, patch

from api.football_api import FootballProvider


class ApiFootballProviderPortabilityTests(unittest.TestCase):
    API_KEY = "api-football-mock-key"

    def test_windows_curl_exe_resolution(self):
        windows_curl = r"C:\Windows\System32\curl.exe"

        with patch(
            "api.curl_json_client.shutil.which",
            side_effect=lambda candidate: (
                windows_curl if candidate == "curl.exe" else None
            ),
        ) as which:
            provider = FootballProvider(self.API_KEY)

        self.assertEqual(provider.curl_executable, windows_curl)
        self.assertEqual(
            which.call_args_list,
            [call("curl"), call("curl.exe")],
        )

    def test_linux_curl_resolution(self):
        linux_curl = "/usr/bin/curl"

        with patch(
            "api.curl_json_client.shutil.which",
            return_value=linux_curl,
        ) as which:
            provider = FootballProvider(self.API_KEY)

        self.assertEqual(provider.curl_executable, linux_curl)
        which.assert_called_once_with("curl")

    def test_resolved_executable_auth_header_and_shell_safety(self):
        resolved_curl = r"C:\Tools\curl.exe"
        completed = Mock(
            returncode=0,
            stdout=json.dumps(
                {"response": [{"team": "Atlético Mineiro"}]},
                ensure_ascii=False,
            ).encode("utf-8"),
            stderr=b"",
        )

        with patch(
            "api.curl_json_client.shutil.which",
            return_value=resolved_curl,
        ), patch(
            "api.curl_json_client.subprocess.run",
            return_value=completed,
        ) as run:
            provider = FootballProvider(self.API_KEY)
            response = provider.get_today_fixtures()

        command = run.call_args.args[0]
        self.assertEqual(command[0], resolved_curl)
        self.assertEqual(
            command[command.index("--header") + 1],
            f"x-apisports-key: {self.API_KEY}",
        )
        self.assertEqual(
            sum(self.API_KEY in argument for argument in command),
            1,
        )
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(
            response,
            [{"team": "Atlético Mineiro"}],
        )

    def test_api_errors_redact_authentication_value(self):
        with patch(
            "api.curl_json_client.shutil.which",
            return_value="/mock/curl",
        ):
            provider = FootballProvider(self.API_KEY)

        with patch.object(
            provider.curl_client,
            "request_json",
            return_value={
                "errors": f"Rejected x-apisports-key: {self.API_KEY}"
            },
        ):
            with self.assertRaises(RuntimeError) as captured:
                provider.get_status()

        message = str(captured.exception)
        self.assertIn("API Error", message)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn(self.API_KEY, message)

    def test_retry_behavior_is_preserved_without_network(self):
        successful = {"response": [{"fixture": {"id": 99}}]}

        with patch(
            "api.curl_json_client.shutil.which",
            return_value="/mock/curl",
        ):
            provider = FootballProvider(self.API_KEY)

        with patch.object(
            provider.curl_client,
            "request_json",
            side_effect=[
                RuntimeError("mock transient failure"),
                successful,
            ],
        ) as request, patch(
            "api.football_api.time.sleep"
        ) as sleep:
            response = provider.get_fixtures_by_league(1, 2026)

        self.assertEqual(response, successful["response"])
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
