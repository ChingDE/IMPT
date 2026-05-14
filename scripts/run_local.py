"""
scripts/run_local.py
Starts the FastAPI development server with auto-reload.
Use this for local development — NOT for production.

Usage:
    PYTHONPATH=. python scripts/run_local.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set local dev defaults if not already configured
os.environ.setdefault("IMPT_DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./impt_local.db")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///./impt_local.db")
os.environ.setdefault("SECRET_KEY", "local-dev-secret-key-not-for-production-32c")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000")
os.environ.setdefault("UPLOAD_DIR", "./uploads")

import uvicorn

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  IMPT Local Development Server")
    print("  API:  http://127.0.0.1:8000")
    print("  Docs: http://127.0.0.1:8000/docs")
    print("  DB:   SQLite (impt_local.db)")
    print("="*55 + "\n")

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
