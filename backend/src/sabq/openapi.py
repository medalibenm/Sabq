"""Write the API description for the frontend to docs/openapi.json (checked by the tests).

Run after changing an endpoint: cd backend && uv run python -m sabq.openapi
"""

import json
from pathlib import Path

TARGET = Path(__file__).resolve().parents[3] / "docs" / "openapi.json"


def main() -> None:
    from sabq.app import app

    text = json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET}")


if __name__ == "__main__":
    main()
