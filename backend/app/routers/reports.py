"""Export endpoints: generate a report in the background and download it.

The MVP uses FastAPI ``BackgroundTasks`` for the async part (see README): the API
contract (``report_id`` + ``status`` polling) is the same one a Celery/RQ worker
would implement later, so the frontend does not change when the queue is upgraded.
"""

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import API_PREFIX
from app.database import SessionLocal, get_db
from app.deps import get_current_user, get_owned_dataset
from app.models import AnalysisResult, Chart, Dataset, ExportedReport, User
from app.schemas import ExportRequest, ExportResponse, ReportStatusResponse
from app.services.chart_service import build_chart_data
from app.services.data_service import read_dataframe
from app.services.export_service import build_report

router = APIRouter(tags=["reports"])

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

        analyses: List[Dict[str, Any]] = []
        if analysis_ids:
            records = (
                db.query(AnalysisResult)
                .filter(
                    AnalysisResult.dataset_id == dataset.id,
                    AnalysisResult.id.in_(analysis_ids),
                )
                .order_by(AnalysisResult.id)
                .all()
            )
            analyses = [record.to_dict() for record in records]

        charts: List[Dict[str, Any]] = []
        frame = None
        if chart_ids:
            records = (
                db.query(Chart)
                .filter(Chart.dataset_id == dataset.id, Chart.id.in_(chart_ids))
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
                    if frame is None:
                        frame = read_dataframe(dataset.storage_path)
                    try:
                        chart_data = build_chart_data(
                            frame, record.chart_type, payload["config"]
                        )
                    except (ValueError, TypeError):
                        chart_data = {}
                payload["chart_data"] = chart_data
                charts.append(payload)

        try:
            path = build_report(
                report_id, file_format, dataset.to_summary_dict(), analyses, charts
            )
        except Exception as exc:  # noqa: BLE001 - surface any writer failure
            report.status = "failed"
            report.error_message = str(exc)
        else:
            report.storage_path = str(path)
            report.status = "completed"
        db.commit()
    finally:
        db.close()


def _assert_ids_belong(
    db: Session,
    dataset: Dataset,
    model: Any,
    ids: List[int],
    label: str,
) -> None:
    if not ids:
        return
    owned = {
        row[0]
        for row in db.query(model.id)
        .filter(model.dataset_id == dataset.id, model.id.in_(ids))
        .all()
    }
    missing = sorted(set(ids) - owned)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown {label} ids for this dataset: {missing}",
        )


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
    dataset = get_owned_dataset(dataset_id, db, user, require_file=False)
    _assert_ids_belong(
        db, dataset, AnalysisResult, payload.include_analysis_ids, "analysis"
    )
    _assert_ids_belong(db, dataset, Chart, payload.include_chart_ids, "chart")

    report = ExportedReport(
        dataset_id=dataset.id,
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
    report = db.get(ExportedReport, report_id)
    if report is None or report.user_id != user.id:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report_id": report.id,
        "dataset_id": report.dataset_id,
        "file_format": report.file_format,
        "status": report.status,
        "error_message": report.error_message,
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
    report = db.get(ExportedReport, report_id)
    if report is None or report.user_id != user.id:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report is still being generated, try again shortly",
        )
    if report.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=report.error_message or "Report generation failed",
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
    dataset = get_owned_dataset(dataset_id, db, user, require_file=False)
    records = (
        db.query(ExportedReport)
        .filter(ExportedReport.dataset_id == dataset.id)
        .order_by(ExportedReport.id.desc())
        .all()
    )
    return [
        {
            **record.to_dict(),
            "download_url": f"{API_PREFIX}/reports/{record.id}/download",
        }
        for record in records
    ]

