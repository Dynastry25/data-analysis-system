"""Web scraping: fetch a page and turn its HTML tables into tabular data.

The contract with the rest of the platform is deliberately small:

- ``fetch_page`` downloads one URL. Only public ``http(s)`` addresses are
  allowed (the check runs again on every redirect hop, so a public page cannot
  bounce the server to its own internals), the content must look like a web
  page, and the body is capped at ``SCRAPE_MAX_BYTES``.
- ``extract_tables`` parses the HTML with pandas' lxml reader into plain
  DataFrames, in document order. That order is the contract between the two
  endpoints: preview index N and import index N are the same table as long as
  the page has not changed, so no server-side state sits between them.

Everything after that — auth, project permissions, profiling, storage — is the
existing dataset pipeline (``ingest_upload``): a scraped table becomes an
ordinary CSV upload the moment it exists, never a second kind of dataset.
"""

import ipaddress
import re
import socket
from dataclasses import dataclass
from io import StringIO
from typing import Any, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
import pandas as pd
from bs4 import BeautifulSoup

from app.config import (
    SCRAPE_MAX_BYTES,
    SCRAPE_MAX_REDIRECTS,
    SCRAPE_MAX_TABLES,
    SCRAPE_TIMEOUT_SECONDS,
)

# Sample rows per table in a preview response. Small on purpose: the preview
# answers "is this the table I want?", not "show me the data".
SCRAPE_PREVIEW_ROWS = 10

# Honest about what it is — sites that block bots should be able to say no in
# their logs rather than to an anonymous client.
USER_AGENT = "StatFlow/0.1 (web table importer)"

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_URL_LENGTH = 2048
# What pandas labels a column whose header cell was empty ("Unnamed: 0").
# Readable as "no heading", so this maps it to the same fallback a table
# without any header row gets, rather than showing the placeholder as a name.
_UNNAMED_HEADER = re.compile(r"^Unnamed: \d+$")


class ScrapeError(ValueError):
    """A scraping failure the caller can act on; routers map it to HTTP 400."""


@dataclass(frozen=True)
class FetchedPage:
    final_url: str
    html: str
    title: Optional[str]


@dataclass(frozen=True)
class ScrapedTable:
    """One ``<table>`` as it will become a dataset."""

    index: int
    frame: pd.DataFrame
    columns: List[str]


# ---------------------------------------------------------------- fetching


def validate_scrape_url(url: str) -> str:
    """Return ``url`` normalised for fetching, or raise ``ScrapeError``.

    Guards, all SSRF-relevant: http/https only, a real host, a sane port, and a
    host that resolves *exclusively* to public addresses (loopback, private,
    link-local, CGNAT, multicast — anything not ``is_global`` — is refused, and
    IPv4-mapped IPv6 forms like ``::ffff:127.0.0.1`` are unwrapped first so
    they cannot slip through). ``fetch_page`` calls this again for every
    redirect hop.

    DNS is resolved here and again by the TCP connect that follows; a rebinding
    race between the two is the one gap left open, accepted for an MVP import
    tool that fetches pages its own users submit.
    """
    candidate = (url or "").strip()
    if not candidate:
        raise ScrapeError("Enter a URL to fetch")
    if len(candidate) > _MAX_URL_LENGTH:
        raise ScrapeError("That URL is too long")
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https"):
        raise ScrapeError("Only http:// and https:// URLs can be fetched")
    if not parsed.hostname:
        raise ScrapeError("That URL has no host name")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ScrapeError("That URL has an invalid port") from exc
    _assert_public_host(parsed.hostname, port)
    # The fragment is never sent over the wire; dropping it keeps preview and
    # import asking for byte-identical resources.
    return urlunparse(parsed._replace(fragment=""))


def _assert_public_host(host: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ScrapeError(f"Could not resolve the host '{host}'") from exc
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise ScrapeError(f"Could not resolve the host '{host}'")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ScrapeError(f"'{address}' is not a valid address") from exc
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if not ip.is_global:
            raise ScrapeError(
                "That URL points to a private or internal address, which is not allowed"
            )


def fetch_page(url: str) -> FetchedPage:
    """GET ``url`` and return the decoded HTML, following at most five hops.

    Redirects are followed manually instead of letting httpx follow them, so
    ``validate_scrape_url`` can re-check *every* destination: the classic SSRF
    trick is a public URL that 302s to ``http://169.254.169.254/``.
    """
    current = url
    with httpx.Client(
        follow_redirects=False,
        timeout=SCRAPE_TIMEOUT_SECONDS,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        },
    ) as client:
        for _hop in range(SCRAPE_MAX_REDIRECTS + 1):
            target = validate_scrape_url(current)
            try:
                with client.stream("GET", target) as response:
                    status = response.status_code
                    if status in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise ScrapeError(
                                f"The site redirected without a Location header (HTTP {status})"
                            )
                        current = urljoin(target, location)
                        continue
                    if status >= 400:
                        raise ScrapeError(f"The site returned HTTP {status}")
                    content_type = response.headers.get("content-type") or ""
                    media_type = content_type.split(";")[0].strip().lower()
                    if media_type and not _is_html_content(media_type):
                        raise ScrapeError(
                            f"That URL is not a web page (content type: {media_type})"
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > SCRAPE_MAX_BYTES:
                            raise ScrapeError(
                                "The page is larger than "
                                f"{SCRAPE_MAX_BYTES // (1024 * 1024)}MB"
                            )
                    raw = bytes(body)
                    declared_charset = _charset_from(content_type)
            except ScrapeError:
                raise
            except httpx.TimeoutException as exc:
                raise ScrapeError("The site did not respond in time") from exc
            except httpx.InvalidURL as exc:
                raise ScrapeError("That URL cannot be fetched") from exc
            except httpx.HTTPError as exc:
                raise ScrapeError(
                    f"Could not fetch the page ({exc.__class__.__name__})"
                ) from exc
            html = _decode(raw, declared_charset)
            return FetchedPage(final_url=target, html=html, title=_page_title(html))
    raise ScrapeError(f"The site redirected more than {SCRAPE_MAX_REDIRECTS} times")


def _is_html_content(media_type: str) -> bool:
    return media_type.startswith("text/") or media_type in {
        "application/xhtml+xml",
        "application/xml",
    }


def _charset_from(content_type: str) -> Optional[str]:
    for part in content_type.split(";")[1:]:
        key, separator, value = part.strip().partition("=")
        if separator and key.lower() == "charset":
            return value.strip().strip("\"'")
    return None


def _decode(raw: bytes, declared_charset: Optional[str]) -> str:
    for encoding in (declared_charset, "utf-8"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    # Never raises: a mislabelled legacy page becomes readable-with-replacements
    # rather than a 500 the user cannot act on.
    return raw.decode("utf-8", errors="replace")


def _page_title(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    if not soup.title:
        return None
    text = " ".join(soup.title.get_text(separator=" ", strip=True).split())
    return text[:300] or None


def extract_tables(html: str) -> List[ScrapedTable]:
    """Parse every readable ``<table>`` in document order.

    pandas' lxml reader decides what counts as the header row — a leading row
    of pure ``<th>`` cells or an explicit ``<thead>`` — the way a reader would,
    including expanding ``colspan`` and repeating a header across a multi-row
    ``<thead>`` into tuple names. This function then normalises what pandas
    produced: tuple headers are flattened to ``"Group / a"``, blank names get
    ``column_n`` fallbacks, duplicates get stable ``_2`` suffixes, and columns
    that came out entirely empty (a malformed row spilling past the table's
    width) are dropped as markup noise.

    The order returned here IS the contract between /scrape/preview and
    /scrape/import: both call this, so index N names the same table on both
    calls while the page is unchanged. No HTML is cached in between.
    """
    try:
        # `header=None` would say "no header row", but pandas' lxml reader has
        # already split a leading <th> row off before that parameter applies —
        # verified behaviour, and the reason this does not re-implement header
        # detection on top of BeautifulSoup.
        frames = pd.read_html(
            StringIO(html), header=None, displayed_only=False, flavor="lxml"
        )
    except ValueError as exc:
        # pandas reports "No tables found" both for a page without tables and
        # for tables it could not read; BeautifulSoup tells the two apart so
        # the user hears the difference.
        found = len(BeautifulSoup(html, "html.parser").find_all("table"))
        if found:
            raise ScrapeError(
                f"The page has {found} table(s), but none could be read as data"
            ) from exc
        raise ScrapeError("This page has no HTML tables to import") from exc
    if not frames:
        raise ScrapeError("This page has no HTML tables to import")

    tables: List[ScrapedTable] = []
    for index, frame in enumerate(frames[:SCRAPE_MAX_TABLES]):
        normalised = _normalise_table(frame)
        tables.append(
            ScrapedTable(
                index=index,
                frame=normalised,
                columns=[str(column) for column in normalised.columns],
            )
        )
    return tables


def _normalise_table(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = _unique_names(
        [_column_name(value, position) for position, value in enumerate(frame.columns)]
    )
    frame = frame.dropna(axis=1, how="all")
    return frame.reset_index(drop=True)


def _column_name(value: Any, position: int) -> str:
    if isinstance(value, tuple):  # MultiIndex: a multi-row <thead>
        parts: List[str] = []
        for part in value:
            text = _text(part)
            if text and text not in parts:
                parts.append(text)
        return " / ".join(parts) or f"column_{position + 1}"
    if not isinstance(value, str):
        # pandas' positional marker (0, 1, …) for a table with no heading row —
        # a number, not a name the page actually wrote. Real heading cells always
        # arrive as strings, even when they contain digits.
        return f"column_{position + 1}"
    text = value.strip()
    if _UNNAMED_HEADER.match(text):
        text = ""
    return text or f"column_{position + 1}"


def _text(value: Any) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return str(value).strip()


def _unique_names(names: List[str]) -> List[str]:
    used = set()
    unique: List[str] = []
    for name in names:
        candidate, suffix = name, 2
        while candidate in used:
            candidate = f"{name}_{suffix}"
            suffix += 1
        used.add(candidate)
        unique.append(candidate)
    return unique


# ------------------------------------------------------------------ output


def table_to_csv(frame: pd.DataFrame) -> bytes:
    """UTF-8 CSV bytes, so from here on the table is an ordinary upload."""
    return frame.to_csv(index=False).encode("utf-8")


def default_import_name(url: str, table_index: int) -> str:
    """``example.org-table-2.csv`` — recognisable in the dataset list."""
    host = urlparse(url).hostname or "web"
    safe_host = re.sub(r"[^a-z0-9.-]+", "-", host.lower()).strip(".-") or "web"
    return f"{safe_host}-table-{table_index + 1}.csv"


