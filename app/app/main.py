"""
Application startup — starts the FastAPI server and opens the browser.
Called from the project-root main.py.
"""

import sys
import time
import threading
import webbrowser

import uvicorn

from app.config import SERVER_HOST, SERVER_PORT
from app.server import app_inst


def _open_browser(host: str, port: int, delay: float = 1.5):
    """Open the default browser after the server has had time to start."""
    time.sleep(delay)
    webbrowser.open(f"http://{host}:{port}")


def start():
    print("=" * 60)
    print("  Mail@AI — Power Platform Message Center")
    print("=" * 60)
    print(f"  URL  : http://{SERVER_HOST}:{SERVER_PORT}")
    print("  Stop : Ctrl+C")
    print()

    threading.Thread(
        target=_open_browser,
        args=(SERVER_HOST, SERVER_PORT),
        daemon=True,
    ).start()

    uvicorn.run(
        app_inst,
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="warning",
    )
