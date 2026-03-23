#!/usr/bin/env python3
"""
Create .venv if missing, then pip install -r requirements.txt.
Run once per machine (or after deleting .venv):  python bootstrap.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQ = ROOT / "requirements.txt"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def main() -> None:
    if not REQ.is_file():
        print(f"Missing {REQ.name} — create it first.", file=sys.stderr)
        sys.exit(1)

    py = venv_python()
    if VENV.is_dir() and not py.is_file():
        print(
            f"This .venv was not created on this OS (no {py}).\n"
            "Delete the .venv folder and run: python bootstrap.py",
            file=sys.stderr,
        )
        sys.exit(1)

    if not VENV.is_dir():
        print(f"Creating venv: {VENV}")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

    print("Installing / updating dependencies …")
    subprocess.run([str(py), "-m", "pip", "install", "-U", "pip"], check=True)
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(REQ)], check=True)
    print(f"Done. Run the server:  {py} backend/app.py")


if __name__ == "__main__":
    main()
