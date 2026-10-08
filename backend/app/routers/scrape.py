"""Web scraping endpoints: preview a page's HTML tables, import one as a dataset.

Both endpoints are stateless between them: each fetches the URL and re-runs the
same deterministic parse, so ``table_index`` means the same table on both calls
while the page is unchanged. Auth and project placement are delegated entirely
to ``ingest_upload`` — a scraped dataset gets no special privileges and no
parallel storage path.
"""

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import SCRAPE_MAX_ROWS
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers.datasets import ingest_upload
from app.schemas import (
    ScrapeImportRequest,
    ScrapePreviewRequest,
    ScrapePreviewResponse,
    ScrapeTablePreview,
    UploadResponse,
)
from app.services import scrape_service
from app.services.data_service import MemoryUpload, dataframe_records
from app.services.scrape_service import ScrapeError

router = APIRouter(prefix="/scrape", tags=["scrape"])


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def _fetch_tables(url: str):
    """Fetch + parse, or raise the HTTP 400 the user can act on."""
    try:
        page = scrape_service.fetch_page(url)
        tables = scrape_service.extract_tables(page.html)
    except ScrapeError as exc:
        raise _bad_request(str(exc)) from exc
    return page, tables


@router.post("/preview", response_model=ScrapePreviewResponse)
def preview_tables(
    payload: ScrapePreviewRequest,
    user: User = Depends(get_current_user),
) -> ScrapePreviewResponse:
    """Fetch the page and list its tables with a small sample of each row.

    Enough to choose by — column names, row counts and the first rows — without
    shipping the whole page. The URL must be re-submitted on import; nothing
    about this response is stored server-side.
    """
    page, tables = _fetch_tables(payload.url)
    previews = [
        ScrapeTablePreview(
            index=table.index,
            row_count=int(table.frame.shape[0]),
            column_count=int(table.frame.shape[1]),
            columns=table.columns,
            preview_rows=dataframe_records(
                table.frame.head(scrape_service.SCRAPE_PREVIEW_ROWS)
            ),
        )
        for table in tables
    ]
    return ScrapePreviewResponse(
        url=payload.url,
        final_url=page.final_url,
        title=page.title,
        table_count=len(previews),
        tables=previews,
    )


@router.post("/import", response_model=UploadResponse)
def import_table(
    payload: ScrapeImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Turn one previewed table into an ordinary dataset (CSV under the hood).

    The table is serialised to CSV bytes and handed to ``ingest_upload``, which
    performs the same extension check, size cap, profiling and project
    permission checks as a picked file — so from the database's point of view
    there is nothing to distinguish this upload, and every downstream stage
    (cleaning, statistics, charts, export) works unchanged.
    """
    page, tables = _fetch_tables(payload.url)

    if payload.table_index >= len(tables):
        raise _bad_request(
            f"The page now has {len(tables)} readable table(s); "
            f"table {payload.table_index + 1} is no longer there. "
            "Fetch the preview again."
        )

    table = tables[payload.table_index]
    frame = table.frame
    if frame.shape[0] == 0:
        raise _bad_request("That table has column headings but no data rows")
    if frame.shape[1] == 0:
        raise _bad_request("That table has no usable columns")
    if frame.shape[0] > SCRAPE_MAX_ROWS:
        raise _bad_request(
            f"That table has {frame.shape[0]:,} rows; the limit for a scraped "
            f"table is {SCRAPE_MAX_ROWS:,}. Download it as a file instead."
        )

    filename = payload.filename or scrape_service.default_import_name(
        page.final_url, payload.table_index
    )
    # The bytes are CSV whatever the user typed, so the extension has to say
    # .csv — a name ending in .xlsx would pass the extension check and then
    # fail to parse, which is a worse error than quietly renaming.
    if not filename.lower().endswith(".csv"):
        filename = f"{Path(filename).stem or 'scraped-table'}.csv"
    filename = Path(filename).name  # never let a name escape its storage folder

    upload = MemoryUpload(filename, scrape_service.table_to_csv(frame))
    return ingest_upload(db, user, upload, payload.project_id)
