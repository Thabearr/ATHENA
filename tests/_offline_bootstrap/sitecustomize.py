"""Inherited pytest-only child bootstrap. No environment opt-out exists."""
from pathlib import Path
import sys

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from offline_transport import install

    install()
except Exception as error:
    raise SystemExit("child pytest offline boundary failed to activate") from error
