"""Generate OpenAPI fixture from FastAPI app."""

import json
from pathlib import Path

from civilai_platform.app import create_app

OUT = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.json"


def main() -> None:
    app = create_app()
    schema = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
