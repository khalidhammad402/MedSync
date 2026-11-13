"""MedSync command runner (replaces the Makefile on machines without `make`).

    python run.py setup    create .venv and install dependencies
    python run.py run      start the app on http://localhost:8000
    python run.py test     run the test suite
    python run.py demo     reset the data, start the app and open the scripted demo
    python run.py reset    restore the demo data
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PORT = os.environ.get("MEDSYNC_PORT", "8000")
HTMX = ROOT / "app" / "l8_ui" / "static" / "htmx.min.js"
HTMX_URL = "https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js"


def python() -> str:
    return str(PY) if PY.exists() else sys.executable


def sh(*args: str) -> int:
    return subprocess.call(list(args), cwd=ROOT)


def setup() -> int:
    if sys.version_info < (3, 11):
        print("MedSync needs Python 3.11 or newer.")
        return 1
    if not PY.exists():
        sh(sys.executable, "-m", "venv", str(VENV))
    code = sh(str(PY), "-m", "pip", "install", "-q", "-r", "requirements.txt")
    if not HTMX.exists():  # shipped in the repo; only fetched if someone deleted it
        import urllib.request
        urllib.request.urlretrieve(HTMX_URL, HTMX)
    if code == 0:
        code = reset()
        print("Setup complete. Start with:  python run.py run")
    return code


def reset() -> int:
    return sh(python(), "-m", "app.l1_data.seed")


def run(open_path: str | None = None) -> int:
    if open_path:
        threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{PORT}{open_path}")).start()
    print(f"MedSync is starting on http://localhost:{PORT}  (Ctrl+C to stop)")
    return sh(python(), "-m", "uvicorn", "app.main:app", "--port", PORT, "--log-level", "warning")


def test() -> int:
    return sh(python(), "-m", "pytest", "-q")


def demo() -> int:
    reset()
    return run("/consult?demo=start")


COMMANDS = {"setup": setup, "run": run, "test": test, "demo": demo, "reset": reset}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    sys.exit(COMMANDS[name]() or 0)
