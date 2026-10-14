"""Job processor service for executing background jobs (Feature 25)."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import REPORTS_DIR
from app.database import SessionLocal
from app.models import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    AnalysisRun,
    Chart,
    Dataset,
    DatasetVersion,
    ExportedReport,
    Job,
    User,
)
from app.services.chart_service import build_chart_data
from app.services.export_service import build_report
from app.statflow import stats_engine, version_store
from app.statflow.version_store import VersionError

logger = logging.getLogger(__name__)

REPORT_FAILURE_MESSAGE = "Report generation failed. Please try again."


def update_job_progress(job_id: int, progress: int, status: JobStatus, result: Optional[Dict] = None, error: Optional[str] = None) -> None:
    """Update job progress in database."""
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            job.progress = progress
            job.status = status
            if result:
                job.result = result
            if error:
                job.error_message = error
            if status in (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED):
                job.completed_at = datetime.now(timezone.utc)
            elif status == JOB_STATUS_RUNNING and job.started_at is None:
                job.started_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def process_analysis_job(job_id: int) -> None:
    """Process an analysis job."""
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        payload = job.payload
        dataset_id = job.dataset_id
        analysis_type = payload.get("analysis_type")
        parameters = payload.get("parameters", {})
        dataset_version = payload.get("dataset_version")
        save = payload.get("save", True)

        update_job_progress(job_id, 10, JOB_STATUS_RUNNING)

        dataset = db.get(Dataset, dataset_id)
        if not dataset:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error="Dataset not found")
            return

        try:
            record, frame = version_store.load_version_frame(db, dataset, dataset_version)
            update_job_progress(job_id, 30, JOB_STATUS_RUNNING)

            result = stats_engine.run_analysis(frame, analysis_type, parameters)
            update_job_progress(job_id, 80, JOB_STATUS_RUNNING)

            response = {
                "dataset_id": dataset.id,
                "dataset_version": int(record.version),
                "dataset_version_id": record.id,
                "analysis_type": analysis_type,
                "status": result.get("status"),
                "result": result,
                "analysis_id": None,
            }

            if save:
                run = AnalysisRun(
                    dataset_id=dataset.id,
                    dataset_version=int(record.version),
                    dataset_version_id=record.id,
                    analysis_type=analysis_type,
                    status=str(result.get("status")),
                    parameters=parameters,
                    result=result,
                )
                db.add(run)
                dataset.status = "analyzed"
                db.commit()
                db.refresh(run)
                response["analysis_id"] = run.id
                response["created_at"] = run.created_at.isoformat() if run.created_at else None

            update_job_progress(job_id, 100, JOB_STATUS_COMPLETED, result=response)

        except (stats_engine.AnalysisError, VersionError, ValueError) as exc:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error=str(exc))

    finally:
        db.close()


def process_report_export_job(job_id: int) -> None:
    """Process a report export job."""
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        payload = job.payload
        report_id = payload.get("report_id")
        file_format = payload.get("file_format")
        analysis_ids = payload.get("analysis_ids", [])
        chart_ids = payload.get("chart_ids", [])

        update_job_progress(job_id, 10, JOB_STATUS_RUNNING)

        report = db.get(ExportedReport, report_id)
        if not report:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error="Report not found")
            return

        dataset = db.get(Dataset, report.dataset_id)
        if not dataset:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error="Dataset no longer exists")
            report.status = "failed"
            report.error_message = "Dataset no longer exists"
            db.commit()
            return

        try:
            if report.dataset_version_id is None:
                raise VersionError("Report source version is unavailable")
            report_version = db.get(DatasetVersion, report.dataset_version_id)
            if not report_version or report_version.dataset_id != dataset.id:
                raise VersionError("Report source version is unavailable")

            update_job_progress(job_id, 20, JOB_STATUS_RUNNING)

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

            update_job_progress(job_id, 40, JOB_STATUS_RUNNING)

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
                    # `build_report` reads `chart_data` as a sibling of `config`,
                    # not nested inside it. Keeping the original payload shape
                    # matters: a report with charts silently drops them otherwise.
                    payload["chart_data"] = chart_data
                    charts.append(payload)

            update_job_progress(job_id, 60, JOB_STATUS_RUNNING)

            dataset_summary = {
                "id": dataset.id,
                "original_filename": dataset.original_filename,
                "file_type": dataset.file_type,
                "row_count": int(report_version.row_count or 0),
                "column_count": int(report_version.column_count or 0),
                "current_version": int(report_version.version),
                "status": report_version.label or "versioned snapshot",
                "uploaded_at": dataset.uploaded_at.isoformat() if dataset.uploaded_at else None,
            }

            path = build_report(report_id, file_format, dataset_summary, analyses, charts)

            update_job_progress(job_id, 90, JOB_STATUS_RUNNING)

            report.storage_path = str(path)
            report.status = "completed"
            db.commit()

            update_job_progress(job_id, 100, JOB_STATUS_COMPLETED, result={"download_url": f"/api/v1/reports/{report_id}/download"})

        except Exception as exc:
            logger.exception("Report generation failed for report %s", report_id)
            report.status = "failed"
            report.error_message = REPORT_FAILURE_MESSAGE
            db.commit()
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error=str(exc))

    finally:
        db.close()


def process_chart_render_job(job_id: int) -> None:
    """Process a chart rendering job."""
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        payload = job.payload
        dataset_id = job.dataset_id
        chart_type = payload.get("chart_type")
        config = payload.get("config", {})
        dataset_version = payload.get("dataset_version")
        save = payload.get("save", True)

        update_job_progress(job_id, 10, JOB_STATUS_RUNNING)

        dataset = db.get(Dataset, dataset_id)
        if not dataset:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error="Dataset not found")
            return

        try:
            version_record, frame = version_store.load_version_frame(db, dataset, dataset_version)
            update_job_progress(job_id, 30, JOB_STATUS_RUNNING)

            chart_data = build_chart_data(frame, chart_type, config)
            update_job_progress(job_id, 60, JOB_STATUS_RUNNING)

            chart_data.setdefault("meta", {})
            chart_data["meta"].update({
                "dataset_id": dataset.id,
                "dataset_name": dataset.original_filename,
                "dataset_version": int(version_record.version),
                "rows_total": int(frame.shape[0]),
            })

            response = {
                "dataset_id": dataset.id,
                "dataset_version": int(version_record.version),
                "dataset_version_id": version_record.id,
                "chart_type": chart_type,
                "config": config,
                "chart_data": chart_data,
            }

            if save:
                stored_config = {**config, "_chart_data": chart_data}
                record = Chart(
                    dataset_id=dataset.id,
                    dataset_version_id=version_record.id,
                    chart_type=chart_type,
                    config=stored_config,
                )
                db.add(record)
                db.commit()
                db.refresh(record)
                response["chart_id"] = record.id
                response["created_at"] = record.created_at.isoformat() if record.created_at else None

            update_job_progress(job_id, 100, JOB_STATUS_COMPLETED, result=response)

        except (VersionError, ValueError) as exc:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error=str(exc))

    finally:
        db.close()


def process_ml_training_job(job_id: int) -> None:
    """Process an ML training job."""
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        payload = job.payload
        dataset_id = job.dataset_id
        analysis_type = payload.get("analysis_type")  # e.g., "logistic_regression", "random_forest", etc.
        parameters = payload.get("parameters", {})
        dataset_version = payload.get("dataset_version")
        save = payload.get("save", True)

        update_job_progress(job_id, 10, JOB_STATUS_RUNNING)

        dataset = db.get(Dataset, dataset_id)
        if not dataset:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error="Dataset not found")
            return

        try:
            record, frame = version_store.load_version_frame(db, dataset, dataset_version)
            update_job_progress(job_id, 30, JOB_STATUS_RUNNING)

            result = stats_engine.run_analysis(frame, analysis_type, parameters)
            update_job_progress(job_id, 80, JOB_STATUS_RUNNING)

            response = {
                "dataset_id": dataset.id,
                "dataset_version": int(record.version),
                "dataset_version_id": record.id,
                "analysis_type": analysis_type,
                "status": result.get("status"),
                "result": result,
                "analysis_id": None,
            }

            if save:
                run = AnalysisRun(
                    dataset_id=dataset.id,
                    dataset_version=int(record.version),
                    dataset_version_id=record.id,
                    analysis_type=analysis_type,
                    status=str(result.get("status")),
                    parameters=parameters,
                    result=result,
                )
                db.add(run)
                dataset.status = "analyzed"
                db.commit()
                db.refresh(run)
                response["analysis_id"] = run.id
                response["created_at"] = run.created_at.isoformat() if run.created_at else None

            update_job_progress(job_id, 100, JOB_STATUS_COMPLETED, result=response)

        except (stats_engine.AnalysisError, VersionError, ValueError) as exc:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error=str(exc))

    finally:
        db.close()


def process_dataset_clean_job(job_id: int) -> None:
    """Process a dataset cleaning job."""
    # Placeholder for dataset cleaning operations
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        update_job_progress(job_id, 100, JOB_STATUS_COMPLETED, result={"message": "Dataset cleaning not yet implemented"})
    finally:
        db.close()


def process_dataset_transform_job(job_id: int) -> None:
    """Process a dataset transformation job."""
    # Placeholder for dataset transformation operations
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        update_job_progress(job_id, 100, JOB_STATUS_COMPLETED, result={"message": "Dataset transformation not yet implemented"})
    finally:
        db.close()


def process_connection_sync_job(job_id: int) -> None:
    """Pull a connection's data in the background (plan 3.4).

    A scheduled sync runs the same ``connection_service.sync_connection``
    the synchronous endpoint runs, so a background pull is not a
    second implementation that can drift: the version write, the
    history row and the error handling are one code path either way.
    """
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        payload = job.payload or {}
        connection_id = payload.get("connection_id")
        update_job_progress(job_id, 10, JOB_STATUS_RUNNING)

        from app.models import DataConnection
        from app.services import connection_service

        connection = db.get(DataConnection, int(connection_id)) if connection_id else None
        if connection is None:
            update_job_progress(
                job_id, 100, JOB_STATUS_FAILED, error="Connection not found"
            )
            return

        update_job_progress(job_id, 40, JOB_STATUS_RUNNING)
        outcome = connection_service.sync_connection(db, connection)
        if not outcome.get("ok"):
            update_job_progress(
                job_id,
                100,
                JOB_STATUS_FAILED,
                error=outcome["sync"].get("error_message") or "The sync failed",
            )
            return

        update_job_progress(job_id, 100, JOB_STATUS_COMPLETED, result=outcome)
    except Exception as exc:
        update_job_progress(job_id, 100, JOB_STATUS_FAILED, error=str(exc))
    finally:
        db.close()


JOB_PROCESSORS = {
    "analysis": process_analysis_job,
    "report_export": process_report_export_job,
    "chart_render": process_chart_render_job,
    "ml_training": process_ml_training_job,
    "dataset_clean": process_dataset_clean_job,
    "dataset_transform": process_dataset_transform_job,
    "connection_sync": process_connection_sync_job,
}


def process_job(job_id: int) -> None:
    """Main entry point to process a job by ID."""
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            logger.error("Job %d not found", job_id)
            return

        processor = JOB_PROCESSORS.get(job.job_type)
        if not processor:
            update_job_progress(job_id, 100, JOB_STATUS_FAILED, error=f"No processor for job type: {job.job_type}")
            return

        logger.info("Processing job %d (type: %s)", job_id, job.job_type)
        processor(job_id)

    except Exception as exc:
        logger.exception("Error processing job %d", job_id)
        update_job_progress(job_id, 100, JOB_STATUS_FAILED, error=f"Internal error: {exc}")
    finally:
        db.close()