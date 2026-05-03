#!/usr/bin/env python3
"""
scripts/run_local.py
Convenience launcher for local development on Windows.

Usage:
    python scripts/run_local.py
    python scripts/run_local.py --port 8080 --reload
"""

import argparse
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Run IMPT API locally")
    parser.add_argument("--host",   default="127.0.0.1")
    parser.add_argument("--port",   default=8000, type=int)
    parser.add_argument("--reload", action="store_true", default=True)
    parser.add_argument("--no-reload", dest="reload", action="store_false")
    args = parser.parse_args()

    print(f"\n{'═'*55}")
    print("  IMPT API — Local Development Server")
    print(f"  http://{args.host}:{args.port}")
    print(f"  Docs: http://{args.host}:{args.port}/docs")
    print(f"  Health: http://{args.host}:{args.port}/api/health")
    print(f"{'═'*55}\n")

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
