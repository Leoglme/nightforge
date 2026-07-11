"""Start the API with reload."""
from __future__ import annotations

import multiprocessing
import os
import sys

import uvicorn

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

if __name__ == "__main__":
    if sys.platform == "win32":
        multiprocessing.freeze_support()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8010"))
    if port == 8000:
        print(
            "WARNING: le port 8000 est réservé à DevLeadHunter — bascule automatique sur 8010. "
            "Définis PORT=8010 dans api/.env."
        )
        port = 8010

    api_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Starting NightForge API on http://{host}:{port} (reload enabled)")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        reload_delay=0.5,
        reload_dirs=[api_dir],
    )
