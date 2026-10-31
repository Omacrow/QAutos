"""Write the OpenAPI schema for the web client's generated types.

Usage: uv run python scripts/export_openapi.py ../web/src/lib/api/openapi.json
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")
os.environ.setdefault("CLERK_ISSUER", "https://unused.example")
os.environ.setdefault("ENVIRONMENT", "development")

from sqa.main import create_app


def main() -> None:
    out = Path(sys.argv[1])
    schema = create_app().openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
