"""Vercel Serverless entrypoint for FastAPI backend."""
import sys
from pathlib import Path

BACKEND_DIR = str(Path(__file__).resolve().parents[1] / "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app  # noqa: E402, F401
