"""Export endpoints: generate a report in the background and download it.

The MVP uses FastAPI ``BackgroundTasks`` for the async part (see README): the API
contract (``report_id`` + ``status`` polling) is the same one a Celery/RQ worker
would implement later, so the frontend does not change when the queue is upgraded.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import API_PREFIX
from app.database import SessionLocal, get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import AnalysisRun, Chart, Dataset, DatasetVersion, ExportedReport, User
from app.rbac import ORG_ROLE_VIEWER
from app.schemas import ExportRequest, ExportResponse, ReportStatusResponse
from app.services.chart_service import build_chart_data
from app.services.export_service import build_report
from app.statflow import version_store
from app.statflow.version_store import VersionError

router = APIRouter(tags=["reports"])
logger = logging.getLogger(__name__)

REPORT_FAILURE_MESSAGE = "Report generation failed. Please try again."
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def generate_report_task(
    report_id: int, file_format: str, analysis_ids: List[int], chart_ids: List[int]
) -> None:
    """Background job: build the report file and update its status row."""
    db: Session = SessionLocal()
    try:
        report = db.get(ExportedReport, report_id)
        if report is None:
            return
        dataset = db.get(Dataset, report.dataset_id)
        if dataset is None:
            report.status = "failed"
            report.error_message = "Dataset no longer exists"
            db.commit()
            return

        try:
            if report.dataset_version_id is None:
                raise VersionError("Report source version is unavailable")
            report_version = db.get(DatasetVersion, report.dataset_version_id)
            if (
                report_version is None
                or report_version.dataset_id != dataset.id
            ):
                raise VersionError("Report source version is unavailable")

            analyses: List[Dict[str, Any]] = []
            if analysis_ids:
                records = (
                    db.query(AnalysisRun)
                    .filter(
                        AnalysisRun.dataset_id == dataset.id,
                        AnalysisRun.dataset_version_id == report_version.id,
                        AnalysisRun.id.in_(analysis_ids),
                    )
                    .order_by(AnalysisRun.id)
                    .all()
                )
                analyses = [record.to_dict() for record in records]

            charts: List[Dict[str, Any]] = []
            frames: Dict[int, Any] = {}
            if chart_ids:
                records = (
                    db.query(Chart)
                    .filter(
                        Chart.dataset_id == dataset.id,
                        Chart.dataset_version_id == report_version.id,
                        Chart.id.in_(chart_ids),
                    )
                    .order_by(Chart.id)
                    .all()
                )
                for record in records:
                    payload = record.to_dict()
                    payload["config"] = {
                        key: value
                        for key, value in (record.config or {}).items()
                        if key != "_chart_data"
                    }
                    chart_data = (record.config or {}).get("_chart_data")
                    if not chart_data:
                        frame = frames.get(report_version.id)
                        if frame is None:
                            frame = version_store.read_version_file(report_version)
                            frames[report_version.id] = frame
                        try:
                            chart_data = build_chart_data(
                                frame, record.chart_type, payload["config"]
                            )
                        except (ValueError, TypeError):
                            chart_data = {}
                    payload["chart_data"] = chart_data
                    charts.append(payload)

            dataset_summary = {
                "id": dataset.id,
                "original_filename": dataset.original_filename,
                "file_type": dataset.file_type,
                "row_count": int(report_version.row_count or 0),
                "column_count": int(report_version.column_count or 0),
                "current_version": int(report_version.version),
                "status": report_version.label or "versioned snapshot",
                "uploaded_at": (
                    dataset.uploaded_at.isoformat() if dataset.uploaded_at else None
                ),
            }
            path = build_report(
                report_id, file_format, dataset_summary, analyses, charts
            )
        except Exception:
            logger.exception("Report generation failed for report %s", report_id)
            report.status = "failed"
            report.error_message = REPORT_FAILURE_MESSAGE
        else:
            report.storage_path = str(path)
            report.status = "completed"
        db.commit()
    finally:
        db.close()


def _assert_ids_belong(
    db: Session,
    dataset: Dataset,
    version_id: int,
    model: Any,
    ids: List[int],
    label: str,
) -> None:
    if not ids:
        return
    owned = {
        row[0]
        for row in db.query(model.id)
        .filter(
            model.dataset_id == dataset.id,
            model.dataset_version_id == version_id,
            model.id.in_(ids),
        )
        .all()
    }
    missing = sorted(set(ids) - owned)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or incompatible {label} ids for this dataset version: {missing}",
        )


def _authorized_report(
    report_id: int, db: Session, user: User
) -> ExportedReport:
    report = db.get(ExportedReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        get_owned_dataset(
            report.dataset_id,
            db,
            user,
            require_file=False,
            min_role=ORG_ROLE_VIEWER,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(status_code=404, detail="Report not found")
        raise
    return report


@router.post(
    "/datasets/{dataset_id}/export",
    response_model=ExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_export(
    dataset_id: int,
    payload: ExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Queue a PDF/XLSX report with the selected analysis results and charts."""
    dataset = get_owned_dataset(dataset_id, db, user)
    try:
        version_record = version_store.resolve_version(
            db, dataset, payload.dataset_version
        )
    except VersionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _assert_ids_belong(
        db,
        dataset,
        version_record.id,
        AnalysisRun,
        payload.include_analysis_ids,
        "analysis",
    )
    _assert_ids_belong(
        db, dataset, version_record.id, Chart, payload.include_chart_ids, "chart"
    )

    report = ExportedReport(
        dataset_id=dataset.id,
        dataset_version_id=version_record.id,
        user_id=user.id,
        file_format=payload.format,
        storage_path="",
        status="processing",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    background_tasks.add_task(
        generate_report_task,
        report.id,
        payload.format,
        list(payload.include_analysis_ids),
        list(payload.include_chart_ids),
    )
    return {"report_id": report.id, "status": report.status}


@router.get("/reports/{report_id}/status", response_model=ReportStatusResponse)
def report_status(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Poll the status of a generated report (used by the export screen)."""
    report = _authorized_report(report_id, db, user)
    return {
        "report_id": report.id,
        "dataset_id": report.dataset_id,
        "dataset_version": (
            report.dataset_version_record.version
            if report.dataset_version_record is not None
            else None
        ),
        "file_format": report.file_format,
        "status": report.status,
        "error_message": (
            REPORT_FAILURE_MESSAGE if report.status == "failed" else None
        ),
        "download_url": f"{API_PREFIX}/reports/{report.id}/download",
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream a finished report (409 while it is still being generated)."""
    report = _authorized_report(report_id, db, user)
    if report.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report is still being generated, try again shortly",
        )
    if report.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=REPORT_FAILURE_MESSAGE,
        )

    path = Path(report.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file is missing from storage")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(report.file_format, "application/octet-stream"),
        filename=path.name,
    )


@router.get("/datasets/{dataset_id}/reports")
def list_reports(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Reports previously generated for a dataset (export screen history)."""
    dataset = get_owned_dataset(
        dataset_id, db, user, require_file=False, min_role=ORG_ROLE_VIEWER
    )
    records = (
        db.query(ExportedReport)
        .filter(ExportedReport.dataset_id == dataset.id)
        .order_by(ExportedReport.id.desc())
        .all()
    )
    return [
        {
            **record.to_dict(),
            "error_message": (
                REPORT_FAILURE_MESSAGE if record.status == "failed" else None
            ),
            "download_url": f"{API_PREFIX}/reports/{record.id}/download",
        }
        for record in records
    ]

