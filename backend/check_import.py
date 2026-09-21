"""Dev helper: import the FastAPI app and report any import-time error."""

import traceback

try:
    from app.main import app

    print(f"IMPORT OK - {len(app.routes)} routes registered")
except Exception:  # noqa: BLE001 - dev helper
    with open("import_error.log", "w", encoding="utf-8") as handle:
        handle.write(traceback.format_exc())
    print("IMPORT FAILED - see import_error.log")
