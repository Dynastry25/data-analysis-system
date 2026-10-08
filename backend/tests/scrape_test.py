"""Tests for web scraping: URL -> HTML tables -> dataset.

The promise this feature makes: a page with tables on it becomes a normal
dataset — same permissions, same profiling, same storage — and the URL is
treated as untrusted input the whole way (public http(s) only, no redirects
into the server's own network). So the checks go past "the endpoint answered"
to the extracted column names, the stored file reading back, and the SSRF
guards, all without touching the network: ``fetch_page`` is replaced with a
fixture wherever a real fetch would be needed.

Run it with:  python tests/scrape_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- test env
TEST_ROOT = Path(tempfile.mkdtemp(prefix="dap_scrape_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "scrape-test-secret-key"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import scrape_service  # noqa: E402
from app.services.scrape_service import FetchedPage, ScrapeError  # noqa: E402

PASSED = 0

# Two tables: one with a proper <th> header row, one that is all <td> so it
# must come out with fallback names. Plus the no-tables page for the error path.
PAGE_HTML = """
<html><head><title>Regional prices</title></head><body>
<h1>Prices</h1>
<table>
  <tr><th>region</th><th>price</th><th>units</th></tr>
  <tr><td>Coast</td><td>1200</td><td>12</td></tr>
  <tr><td>Lake</td><td>1500</td><td>9</td></tr>
  <tr><td>Highlands</td><td>900</td><td>20</td></tr>
</table>
<table>
  <tr><td>alpha</td><td>1</td></tr>
  <tr><td>beta</td><td>2</td></tr>
</table>
</body></html>
"""

NO_TABLE_HTML = (
    "<html><head><title>Nothing</title></head>"
    "<body><p>No tables on this page.</p></body></html>"
)

HEADER_ONLY_HTML = (
    "<html><head><title>Header only</title></head><body>"
    "<table><tr><th>a</th><th>b</th></tr></table>"
    "</body></html>"
)


def check(condition: bool, message: str) -> None:
    global PASSED
    if condition:
        PASSED += 1
    else:
        print(f"  FAIL: {message}")


def register(client) -> dict:
    email = "scrape@example.com"
    client.post(
        "/api/auth/register",
        json={"full_name": "Scrape Tester", "email": email, "password": "secret123"},
    )
    login = client.post(
        "/api/auth/login", json={"email": email, "password": "secret123"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def fake_page(html: str, title: str = "Regional prices"):
    """A fetch_page stand-in: same contract, no network."""

    def _fetch(url: str) -> FetchedPage:
        return FetchedPage(final_url=url, html=html, title=title)

    return _fetch


def run_checks(client) -> int:
    headers = register(client)
    real_fetch = scrape_service.fetch_page

    print("1) URL guards (no network touched)")

    for bad, why in [
        ("ftp://example.com/data", "a non-http scheme"),
        ("http://127.0.0.1/admin", "the loopback address"),
        ("http://10.0.0.8/x", "a private address"),
        ("http://169.254.169.254/latest/meta-data", "the link-local metadata address"),
        ("http://localhost/x", "the localhost name"),
        ("", "an empty URL"),
    ]:
        try:
            scrape_service.validate_scrape_url(bad)
            check(False, f"validate_scrape_url refuses {why}")
        except ScrapeError:
            check(True, f"validate_scrape_url refuses {why}")

    check(
        scrape_service.validate_scrape_url("https://Example.com/a#frag")
        == "https://Example.com/a",
        "a valid URL is normalised (fragment dropped, host kept)",
    )

    # The endpoint runs the guard itself, before any fetch would happen.
    loopback = client.post(
        "/api/v1/scrape/preview",
        json={"url": "http://127.0.0.1/x"},
        headers=headers,
    )
    check(
        loopback.status_code == 400
        and "private or internal" in loopback.json()["detail"],
        f"preview refuses a loopback URL through the API ({loopback.status_code})",
    )

    print("2) preview")
    scrape_service.fetch_page = fake_page(PAGE_HTML)
    try:
        unauth = client.post(
            "/api/v1/scrape/preview", json={"url": "https://example.com/prices"}
        )
        check(unauth.status_code == 401, f"preview requires a token ({unauth.status_code})")

        preview = client.post(
            "/api/v1/scrape/preview",
            json={"url": "https://example.com/prices"},
            headers=headers,
        )
        check(
            preview.status_code == 200,
            f"preview returns 200 ({preview.status_code}: "
            f"{preview.json().get('detail', '') if preview.status_code != 200 else ''})",
        )
        body = preview.json()
        check(body["table_count"] == 2, "both tables are listed")
        check(body["title"] == "Regional prices", "the page title comes back")
        first = body["tables"][0]
        check(
            first["columns"] == ["region", "price", "units"],
            f"a <th> row becomes the columns ({first['columns']})",
        )
        check(first["row_count"] == 3, "the heading row is not counted as data")
        check(
            bool(first["preview_rows"])
            and first["preview_rows"][0]["region"] == "Coast",
            "preview rows carry real values",
        )
        second = body["tables"][1]
        check(
            second["columns"] == ["column_1", "column_2"],
            f"a table without headings gets column_n names ({second['columns']})",
        )
        check(second["row_count"] == 2, "the headerless table keeps its rows")

        print("3) import")
        imported = client.post(
            "/api/v1/scrape/import",
            json={"url": "https://example.com/prices", "table_index": 0},
            headers=headers,
        )
        check(
            imported.status_code == 200,
            "import returns the upload response "
            f"({imported.status_code}: "
            f"{imported.json().get('detail', '') if imported.status_code != 200 else ''})",
        )
        payload = imported.json()
        check(
            payload.get("original_filename") == "example.com-table-1.csv",
            f"the default name is host+table ({payload.get('original_filename')})",
        )
        check(
            payload["row_count"] == 3 and payload["column_count"] == 3,
            "row and column counts survive the round trip",
        )
        types = {c["name"]: c["data_type"] for c in payload["columns"]}
        check(types.get("price") == "numeric", "profiled exactly like an uploaded CSV")

        detail = client.get(f"/api/datasets/{payload['dataset_id']}", headers=headers)
        check(
            detail.status_code == 200
            and detail.json()["preview_rows"][0]["region"] == "Coast",
            "the stored dataset reads back through the normal endpoint",
        )

        named = client.post(
            "/api/v1/scrape/import",
            json={
                "url": "https://example.com/prices",
                "table_index": 1,
                "filename": "prices.xlsx",
            },
            headers=headers,
        )
        check(
            named.status_code == 200
            and named.json()["original_filename"] == "prices.csv",
            "a filename cannot claim .xlsx for bytes that are CSV",
        )

        missing = client.post(
            "/api/v1/scrape/import",
            json={"url": "https://example.com/prices", "table_index": 9},
            headers=headers,
        )
        check(
            missing.status_code == 400,
            f"a vanished table index is a 400, not a crash ({missing.status_code})",
        )

        scrape_service.fetch_page = fake_page(HEADER_ONLY_HTML, title="Header only")
        hollow = client.post(
            "/api/v1/scrape/import",
            json={"url": "https://example.com/hollow", "table_index": 0},
            headers=headers,
        )
        check(
            hollow.status_code == 400
            and "no data rows" in hollow.json()["detail"],
            "a heading-only table is refused with a reason",
        )

        scrape_service.fetch_page = fake_page(NO_TABLE_HTML, title="Nothing")
        none_found = client.post(
            "/api/v1/scrape/preview",
            json={"url": "https://example.com/empty"},
            headers=headers,
        )
        check(
            none_found.status_code == 400
            and "no HTML tables" in none_found.json()["detail"],
            "a table-less page says so",
        )
    finally:
        scrape_service.fetch_page = real_fetch

    print("4) extraction normalisation")
    multi = scrape_service.extract_tables(
        "<table><thead>"
        '<tr><th colspan="2">Group</th></tr>'
        "<tr><th>a</th><th>b</th></tr>"
        "</thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    )
    check(
        multi[0].columns == ["Group / a", "Group / b"],
        f"a multi-row header flattens ({multi[0].columns})",
    )

    duplicate = scrape_service.extract_tables(
        "<table><tr><th>score</th><th>score</th></tr>"
        "<tr><td>1</td><td>2</td></tr></table>"
    )
    check(
        duplicate[0].columns == ["score", "score.1"],
        f"duplicate header cells never produce duplicate names "
        f"({duplicate[0].columns})",
    )

    # An empty heading becomes pandas' "Unnamed: 0" placeholder, which maps to
    # column_1 — and a real column already called column_1 must not collide.
    placeholder = scrape_service.extract_tables(
        "<table><tr><th></th><th>column_1</th></tr>"
        "<tr><td>1</td><td>2</td></tr></table>"
    )
    check(
        placeholder[0].columns == ["column_1", "column_1_2"],
        f"placeholder names fall back and never collide ({placeholder[0].columns})",
    )

    check(
        scrape_service.default_import_name("https://Example.COM/x/y", 1)
        == "example.com-table-2.csv",
        "the default import name is derived from the host",
    )

    print(f"\n{PASSED} checks passed")
    return 0


def main() -> int:
    # The client is opened as a context manager so the app lifespan runs and
    # creates the SQLite tables, exactly like the other tests in this folder.
    with TestClient(app) as client:
        return run_checks(client)


if __name__ == "__main__":
    sys.exit(main())




