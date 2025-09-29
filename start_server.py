"""Entrypoint to run the FastAPI app using uvicorn.

Usage (inside .venv from project root):
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

This module allows `python start_server.py` as well.
"""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()


