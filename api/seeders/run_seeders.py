"""Run all database seeders in order.

Seeders are idempotent: existing records are skipped when already present.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.database import init_db

SEEDERS: list[tuple[str, str, str]] = [
    ("users", "seeders.user_seeder", "seed_admin_user"),
]


def _load_dotenv() -> None:
    """Load the .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_ROOT / ".env")


def _run_seeder(module_name: str, function_name: str) -> None:
    """
    Import and run a single seeder function.

    Args:
        module_name: Dotted module path.
        function_name: Seeder function name.
    """
    module = importlib.import_module(module_name)
    seed_fn = getattr(module, function_name, None)
    if seed_fn is None:
        raise RuntimeError(f"{module_name} must define {function_name}()")
    seed_fn()


def main() -> None:
    """Ensure the schema then run every seeder."""
    _load_dotenv()

    print("Ensuring base schema from SQLAlchemy models...")
    init_db()
    print("Base schema ensured.\n")

    for seeder_name, module_name, function_name in SEEDERS:
        print(f"Seeding: {seeder_name}")
        _run_seeder(module_name, function_name)
        print()

    print("All seeders complete.")


if __name__ == "__main__":
    main()
