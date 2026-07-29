import os
import subprocess
import sys
import unittest
from pathlib import Path


class HistoricalResultsLoaderInvocationTests(unittest.TestCase):
    REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

    def _assert_help_succeeds(self, command):
        database_path = self.REPOSITORY_ROOT / "database" / "athena.db"
        before = (
            (database_path.stat().st_size, database_path.stat().st_mtime_ns)
            if database_path.exists()
            else None
        )
        environment = os.environ.copy()
        environment["FOOTBALL_DATA_ORG_API_KEY"] = "unused-help-test-key"
        environment["FOOTBALL_API_KEY"] = "unused-help-test-key"

        result = subprocess.run(
            command,
            cwd=self.REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            shell=False,
        )

        after = (
            (database_path.stat().st_size, database_path.stat().st_mtime_ns)
            if database_path.exists()
            else None
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout.lower())
        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertEqual(before, after)

    def test_direct_script_help_is_side_effect_free(self):
        self._assert_help_succeeds(
            [
                sys.executable,
                "workers/historical_results_loader.py",
                "--help",
            ]
        )

    def test_module_help_is_side_effect_free(self):
        self._assert_help_succeeds(
            [
                sys.executable,
                "-m",
                "workers.historical_results_loader",
                "--help",
            ]
        )


if __name__ == "__main__":
    unittest.main()
