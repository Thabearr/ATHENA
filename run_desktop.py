import argparse
import threading
import uvicorn
import webview
import time
import requests
from loguru import logger
from api.server import app

def start_server():
    """Start the FastAPI server in a daemon thread."""
    logger.info("Starting ATHENA local server on port 8500...")
    uvicorn.run(app, host="127.0.0.1", port=8500, log_level="error")

def wait_for_server():
    """Wait until the FastAPI server is responsive."""
    url = "http://127.0.0.1:8500/api/status"
    for _ in range(15):
        try:
            res = requests.get(url)
            if res.status_code == 200:
                logger.success("ATHENA local server is online.")
                return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.5)
    return False

def parse_args(argv=None):
    """Packaging/qualification-only CLI. Normal launches behave exactly as before."""
    parser = argparse.ArgumentParser(description="ATHENA desktop shell.", allow_abbrev=False)
    parser.add_argument(
        "--port02c-smoke",
        action="store_true",
        help="Start the local server, prove readiness, then exit without opening a window.",
    )
    return parser.parse_args(argv)


if __name__ == '__main__':
    smoke = parse_args().port02c_smoke
    # Check if backend server is already online
    if not wait_for_server():
        # Start the backend server if not already running
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        # Wait for the backend to be ready
        if not wait_for_server():
            logger.error("Failed to start local server. Exiting.")
            exit(1)
    else:
        logger.info("ATHENA local server is already active on port 8500.")

    if smoke:
        # Offline packaging smoke: resource/backend initialization is proven
        # by server readiness above. No window, no provider call, clean exit.
        # This switch never alters business authority and is not a product journey.
        logger.info("ATHENA smoke mode: server is online, exiting without UI.")
        raise SystemExit(0)

    import os
    # Launch the Pywebview window pointing to our local HTML file
    ui_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "ui", "index.html"))
    
    logger.info("Launching ATHENA Desktop UI...")
    webview.create_window(
        title="ATHENA | Fullproof Engine",
        url=ui_path,
        width=1100,
        height=750,
        min_size=(750, 550),
        resizable=True,
        background_color="#0b0f19"
    )
    
    # Start the pywebview event loop
    webview.start()
