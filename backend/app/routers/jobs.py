"""Job queue endpoints (Feature 25).

Provides a background job queue with progress tracking for long-running operations.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Job, User
from app.schemas import JobCreate, JobListResponse, JobResponse, JobStatus, JobType, JobUpdate
from app.services.job_processor import process_job

router = APIRouter(tags=["jobs"])
logger = logging.getLogger(__name__)


def _job_payload(record: Job) -> Dict[str, Any]:
    return record.to_dict()


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    auto_start: bool = Query(default=True, description="Automatically start processing the job"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a new background job.

    The job starts in pending status. If auto_start is true (default), a background
    task will begin processing it immediately.
    """
    job = Job(
        user_id=user.id,
        job_type=payload.job_type,
        dataset_id=payload.dataset_id,
        status=JOB_STATUS_PENDING,
        progress=0,
        payload=payload.payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if auto_start:
        background_tasks.add_task(process_job, job.id)

    return _job_payload(job)


@router.get("", response_model=JobListResponse)
def list_jobs(
    job_type: Optional[str] = Query(default=None),
    status_filter: Optional[JobStatus] = Query(default=None, alias="status"),
    dataset_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """List jobs for the current user (or all jobs for platform admins)."""
    from app.models import User as UserModel
    from app.platform_rbac import PLATFORM_ROLE_ADMIN, require_platform_role

    is_platform_admin = False
    try:
        require_platform_role(db, user, PLATFORM_ROLE_ADMIN)
        is_platform_admin = True
    except HTTPException:
        pass

    conditions = []
    if not is_platform_admin:
        conditions.append(Job.user_id == user.id)

    if job_type:
        conditions.append(Job.job_type == job_type)
    if status_filter:
        conditions.append(Job.status == status_filter)
    if dataset_id:
        conditions.append(Job.dataset_id == dataset_id)

    total = int(
        db.query(func.count(Job.id)).filter(*conditions).scalar() or 0
    )
    jobs = (
        db.query(Job)
        .filter(*conditions)
        .order_by(Job.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return JobListResponse(
        items=[_job_payload(job) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get a single job by ID."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ownership (unless platform admin)
    from app.models import User as UserModel
    from app.platform_rbac import PLATFORM_ROLE_ADMIN, require_platform_role

    is_platform_admin = False
    try:
        require_platform_role(db, user, PLATFORM_ROLE_ADMIN)
        is_platform_admin = True
    except HTTPException:
        pass

    if not is_platform_admin and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    return _job_payload(job)


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: int,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update job status, progress, or result (typically called by background worker)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ownership (unless platform admin)
    from app.models import User as UserModel
    from app.platform_rbac import PLATFORM_ROLE_ADMIN, require_platform_role

    is_platform_admin = False
    try:
        require_platform_role(db, user, PLATFORM_ROLE_ADMIN)
        is_platform_admin = True
    except HTTPException:
        pass

    if not is_platform_admin and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this job")

    from datetime import datetime, timezone

    if payload.status is not None:
        job.status = payload.status
        if payload.status == JOB_STATUS_RUNNING and job.started_at is None:
            job.started_at = datetime.now(timezone.utc)
        elif payload.status in (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED):
            job.completed_at = datetime.now(timezone.utc)

    if payload.progress is not None:
        job.progress = payload.progress

    if payload.result is not None:
        job.result = payload.result

    if payload.error_message is not None:
        job.error_message = payload.error_message

    db.commit()
    db.refresh(job)
    return _job_payload(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Cancel a pending or running job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ownership
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this job")

    if job.status not in (JOB_STATUS_PENDING, JOB_STATUS_RUNNING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in status '{job.status}'",
        )

    job.status = JOB_STATUS_CANCELLED
    from datetime import datetime, timezone
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/{job_id}/start", response_model=JobResponse)
def start_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Start processing a pending job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ownership (unless platform admin)
    from app.models import User as UserModel
    from app.platform_rbac import PLATFORM_ROLE_ADMIN, require_platform_role

    is_platform_admin = False
    try:
        require_platform_role(db, user, PLATFORM_ROLE_ADMIN)
        is_platform_admin = True
    except HTTPException:
        pass

    if not is_platform_admin and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to start this job")

    if job.status != JOB_STATUS_PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start job in status '{job.status}'",
        )

    background_tasks.add_task(process_job, job.id)
    return _job_payload(job)


# ---------------------------------------------------------------- WebSocket for real-time progress


@router.websocket("/ws")
async def jobs_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db),
) -> None:
    """WebSocket endpoint for real-time job progress updates.

    Clients can connect and subscribe to job progress events.
    The server broadcasts progress updates when jobs are updated.
    """
    await websocket.accept()
    try:
        while True:
            # Keep connection alive, wait for client messages (subscription requests)
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "subscribe" and message.get("job_id"):
                    # In a production system, you'd store the subscription and
                    # send updates when the job progresses. For now, we'll
                    # send a periodic update for the subscribed job.
                    job_id = message["job_id"]
                    job = db.get(Job, job_id)
                    if job:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "job_progress",
                                    "job_id": job.id,
                                    "progress": job.progress,
                                    "status": job.status,
                                }
                            )
                        )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        # Log error in production
        pass