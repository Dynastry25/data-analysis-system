"""Database and API connectors (plan 3.4).

The strategy's claim was "connect an organisational database" while
ingest was files and scraping only, which caps StatFlow at
personal-data analysis. This is the ingest path that was missing:
Postgres, MySQL, or any REST endpoint that returns JSON.

Three decisions shape everything here:

* **A connection is an ingest path, not a data store.** A sync pulls
  a frame and hands it to the version system, which writes a new
  immutable dataset version. Nothing downstream changes -- the
  lineage view, the remediation, the result cache and the analysis
  history all work on a connected dataset exactly as they do on an
  uploaded one, and the organisation's database stays the system of
  record for its own data.
* **The driver is loaded lazily and its absence is a readable
  error.** A deployment with no Postgres driver can still serve
  every other feature; asking it to connect says which package to
  install rather than raising an ImportError at import time.
* **A query is not assumed to be safe to run as written.** The
  connection stores what the reader typed, and the engine adds a
  LIMIT when the reader did not, because "SELECT * FROM 40 million
  rows" as a first sync is an outage waiting to happen. The reader
  can turn the guard off by writing their own LIMIT, which is a
  deliberate act rather than a default.
"""

import io
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as url_error
from urllib import request as url_request

import pandas as pd

logger = logging.getLogger(__name__)

#: Rows pulled when the reader's query has no LIMIT of its own.
DEFAULT_ROW_LIMIT = 100_000

#: Wall-clock budgets, in seconds. An organisational database that
#: has not answered in this long is a configuration problem, not a
#: slow query, and the reader should be told rather than left
#: waiting on a connection that will never come back.
DB_CONNECT_TIMEOUT = 10
DB_QUERY_TIMEOUT = 60
HTTP_TIMEOUT = 30

_DRIVERS = {
    "postgres": ("postgresql+psycopg", "psycopg (v3) — pip install 'psycopg[binary]'"),
    "mysql": ("mysql+pymysql", "PyMySQL — pip install PyMySQL"),
}


class ConnectorError(ValueError):
    """A connection could not be made or read (mapped to HTTP 400)."""


def required_fields(kind: str) -> List[str]:
    """The config fields each kind needs, for the UI and for validation."""
    if kind == "rest":
        return ["url"]
    return ["host", "port", "database", "user"]


def validate_config(kind: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Check a connection's configuration before it is stored."""
    if kind not in ("postgres", "mysql", "rest"):
        raise ConnectorError(f"Unsupported connection kind '{kind}'")
    missing = [field for field in required_fields(kind) if not config.get(field)]
    if missing:
        raise ConnectorError(
            f"A {kind} connection needs: {', '.join(missing)}"
        )
    if kind == "rest":
        url = str(config["url"])
        if not url.lower().startswith(("http://", "https://")):
            raise ConnectorError("The REST URL must start with http:// or https://")
        return config
    try:
        int(config["port"])
    except (TypeError, ValueError):
        raise ConnectorError("The port must be a number")
    return config


def _ensure_limit(sql: str) -> str:
    """Add a row limit to a query that has none, once and safely."""
    if not sql.strip():
        return sql
    if "limit" in sql.lower():
        return sql
    return f"{sql.rstrip().rstrip(';')} LIMIT {DEFAULT_ROW_LIMIT}"


def _frame_from_db(kind: str, config: Dict[str, Any], password: str) -> pd.DataFrame:
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError, SQLAlchemyError

    dialect, driver_note = _DRIVERS[kind]
    try:
        import importlib.util

        driver = dialect.split("+")[1]
        if importlib.util.find_spec(driver) is None:
            raise ConnectorError(
                f"The {kind} connector needs the {driver} driver: {driver_note}"
            )
    except ConnectorError:
        raise
    except Exception:  # pragma: no cover - defensive
        raise ConnectorError(f"The {kind} connector's driver could not be loaded")

    # The database name is a path segment, so it needs its own slash:
    # `host:5432/app`, not `host:5432app`. A reader who typed a
    # leading slash gets exactly one, because a doubled slash is a
    # connection to a database named "".
    database = str(config["database"]).strip()
    if not database.startswith("/"):
        database = f"/{database}"
    url = (
        f"{dialect}://{config['user']}:{url_request.quote(password, safe='')}@"
        f"{config['host']}:{int(config['port'])}{database}"
    )
    try:
        engine = create_engine(
            url,
            connect_args={"connect_timeout": DB_CONNECT_TIMEOUT},
            pool_pre_ping=True,
        )
    except SQLAlchemyError as exc:  # pragma: no cover - driver-specific
        raise ConnectorError(f"Could not build a {kind} engine: {exc}") from exc

    table = config.get("table")
    query = config.get("query")
    sql = _ensure_limit(str(query)) if query else f"SELECT * FROM {table} LIMIT {DEFAULT_ROW_LIMIT}"
    try:
        with engine.connect() as connection:
            connection = connection.execution_options(
                timeout=DB_QUERY_TIMEOUT
            )
            frame = pd.read_sql(sql, connection)
    except OperationalError as exc:
        raise ConnectorError(
            f"The {kind} query failed. Check the host, the database name and the "
            f"credentials. ({exc.__class__.__name__})"
        ) from exc
    except SQLAlchemyError as exc:
        raise ConnectorError(f"The {kind} query failed: {exc.__class__.__name__}") from exc
    finally:
        engine.dispose()
    return frame


def _frame_from_rest(config: Dict[str, Any], secret_value: str) -> pd.DataFrame:
    """Pull a REST endpoint into a frame.

    JSON is the expected shape (an array of objects, or an object with
    one array inside it); a CSV response body is accepted too, because
    plenty of organisational exports are CSV served over HTTP.
    """
    url = str(config["url"])
    headers = {"Accept": "application/json, text/csv"}
    for key, value in (config.get("headers") or {}).items():
        headers[str(key)] = str(value)
    auth = (config.get("auth") or "").strip()
    if auth:
        headers["Authorization"] = auth
    if secret_value and "Authorization" not in headers:
        headers["Authorization"] = secret_value

    req = url_request.Request(url, headers=headers, method="GET")
    try:
        with url_request.urlopen(req, timeout=HTTP_TIMEOUT) as response:  # noqa: S310 - operator-configured URL
            body = response.read()
            content_type = (response.headers.get("Content-Type") or "").lower()
    except url_error.URLError as exc:
        raise ConnectorError(f"The REST endpoint could not be reached: {exc.reason}") from exc
    except OSError as exc:
        raise ConnectorError(f"The REST endpoint could not be reached: {exc}") from exc

    if not body.strip():
        raise ConnectorError("The endpoint returned an empty body")

    looks_json = "json" in content_type or body[:1] in (b"{", b"[")
    if looks_json:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ConnectorError(
                "The endpoint returned something that is not valid JSON"
            ) from exc
        return pd.DataFrame.from_records(_rows_from_json(payload))

    # A CSV body is the other shape an organisational export takes.
    try:
        return pd.read_csv(io.BytesIO(body))
    except Exception as exc:
        raise ConnectorError(
            f"The endpoint's response could not be read as a table: {exc}"
        ) from exc


def _rows_from_json(payload: Any) -> List[Dict[str, Any]]:
    """The array of records inside a JSON payload, wherever it is."""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        arrays = [value for value in payload.values() if isinstance(value, list)]
        if len(arrays) == 1 and all(isinstance(item, dict) for item in arrays[0]):
            rows = arrays[0]
        elif "data" in payload and isinstance(payload["data"], list):
            rows = payload["data"]
        elif "items" in payload and isinstance(payload["items"], list):
            rows = payload["items"]
        elif "results" in payload and isinstance(payload["results"], list):
            rows = payload["results"]
        else:
            rows = [payload]
    else:
        raise ConnectorError("The JSON response has no array of records")
    if not rows:
        raise ConnectorError("The query returned no rows")
    if not all(isinstance(item, dict) for item in rows):
        raise ConnectorError("The JSON response's rows are not objects")
    return rows


def fetch_frame(
    kind: str, config: Dict[str, Any], password: str = ""
) -> Tuple[pd.DataFrame, int]:
    """Pull a connection's data and return (frame, elapsed_ms)."""
    started = time.perf_counter()
    if kind in _DRIVERS:
        frame = _frame_from_db(kind, config, password)
    elif kind == "rest":
        frame = _frame_from_rest(config, password)
    else:  # pragma: no cover - checked by validate_config
        raise ConnectorError(f"Unsupported connection kind '{kind}'")
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if frame.empty:
        raise ConnectorError("The query ran but returned no rows")
    return frame, elapsed_ms
