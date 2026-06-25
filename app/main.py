"""
Entry point — run this file to start the MC Auto-Analysis web application.

    python main.py

The server starts on http://127.0.0.1:8765 and the browser opens automatically.
The original gemma3_chat.py (CLI version) is left untouched.
"""

from app.main import start

if __name__ == "__main__":
    start()
