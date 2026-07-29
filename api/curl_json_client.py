"""Platform-neutral, UTF-8-safe JSON transport through curl."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Mapping, Sequence


MAX_DIAGNOSTIC_EXCERPT = 240


def bounded_sanitized_excerpt(
    value,
    *,
    sensitive_values: Sequence[str] = (),
) -> str:
    """Return a bounded diagnostic excerpt with credentials redacted."""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif value is None:
        text = ""
    else:
        text = str(value)

    for sensitive_value in sensitive_values:
        if sensitive_value:
            text = text.replace(str(sensitive_value), "[REDACTED]")

    text = re.sub(
        r"(?i)\b(x-auth-token|x-apisports-key)\s*:\s*[^\s,;]+",
        r"\1: [REDACTED]",
        text,
    )
    text = " ".join(text.split())
    if not text:
        return "<empty>"
    if len(text) > MAX_DIAGNOSTIC_EXCERPT:
        return text[:MAX_DIAGNOSTIC_EXCERPT] + "..."
    return text


class CurlJsonClient:
    """Execute curl without a shell and decode provider JSON as UTF-8."""

    def __init__(
        self,
        *,
        connect_timeout_seconds: int = 20,
        request_timeout_seconds: int = 60,
    ):
        self.executable = self._resolve_executable()
        self.connect_timeout_seconds = connect_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds

    @staticmethod
    def _resolve_executable() -> str:
        for candidate in ("curl", "curl.exe"):
            executable = shutil.which(candidate)
            if executable:
                return executable
        raise RuntimeError(
            "The curl executable could not be found on PATH. "
            "Install curl or add it to PATH before using provider APIs."
        )

    def request_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
    ):
        command = [
            self.executable,
            "--silent",
            "--show-error",
            "--location",
            "--http1.1",
            "--compressed",
            "--connect-timeout",
            str(self.connect_timeout_seconds),
            "--max-time",
            str(self.request_timeout_seconds),
        ]
        sensitive_values = []
        for name, value in headers.items():
            header_value = str(value)
            sensitive_values.append(header_value)
            command.extend(["--header", f"{name}: {header_value}"])
        command.append(url)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                shell=False,
            )
        except OSError as error:
            raise RuntimeError(
                "The curl executable could not be started."
            ) from error

        if result.returncode != 0:
            diagnostic = bounded_sanitized_excerpt(
                result.stderr,
                sensitive_values=sensitive_values,
            )
            raise RuntimeError(
                f"Curl request failed with exit code {result.returncode}. "
                f"Diagnostic excerpt: {diagnostic}"
            )

        raw_stdout = result.stdout
        if isinstance(raw_stdout, str):
            decoded = raw_stdout
        else:
            try:
                decoded = (raw_stdout or b"").decode("utf-8")
            except UnicodeDecodeError as error:
                diagnostic = bounded_sanitized_excerpt(
                    raw_stdout,
                    sensitive_values=sensitive_values,
                )
                raise RuntimeError(
                    "Provider response was not valid UTF-8 JSON. "
                    f"Response excerpt: {diagnostic}"
                ) from error

        try:
            return json.loads(decoded)
        except (TypeError, ValueError) as error:
            diagnostic = bounded_sanitized_excerpt(
                decoded,
                sensitive_values=sensitive_values,
            )
            raise RuntimeError(
                "Provider returned invalid JSON. "
                f"Response excerpt: {diagnostic}"
            ) from error


__all__ = [
    "CurlJsonClient",
    "MAX_DIAGNOSTIC_EXCERPT",
    "bounded_sanitized_excerpt",
]
