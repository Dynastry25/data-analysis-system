"""SQLAlchemy models for the Data Analysis Platform MVP.

Mirrors schema.sql (7 related tables). JSONB columns from the PostgreSQL schema are
mapped with the portable ``JSON`` type so the same models work on SQLite (dev) and
PostgreSQL (production).
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    datasets = relationship(
        "Dataset", back_populates="user", cascade="all, delete-orphan"
    )
    reports = relationship(
        "ExportedReport", back_populates="user", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False, default="")
    file_type = Column(String(20), nullable=False)  # csv, xlsx
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    status = Column(String(20), default="uploaded")  # uploaded, cleaned, analyzed
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="datasets")
    columns = relationship(
        "DatasetColumn",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetColumn.id",
    )
    charts = relationship(
        "Chart",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="Chart.id",
    )
    reports = relationship(
        "ExportedReport", back_populates="dataset", cascade="all, delete-orphan"
    )
    versions = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version",
    )
    operations = relationship(
        "DatasetOperation",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetOperation.sequence",
    )
    analysis_runs = relationship(
        "AnalysisRun",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="AnalysisRun.id",
    )

    def to_summary_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "status": self.status,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_name = Column(String(150), nullable=False)
    data_type = Column(String(30))  # numeric, text, date, boolean
    missing_count = Column(Integer, default=0)
    unique_count = Column(Integer)

    dataset = relationship("Dataset", back_populates="columns")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.column_name,
            "column_name": self.column_name,
            "data_type": self.data_type,
            "missing_count": self.missing_count or 0,
            "unique_count": self.unique_count,
        }


class Chart(Base):
    __tablename__ = "charts"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chart_type = Column(String(30), nullable=False)
    config = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="charts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "chart_type": self.chart_type,
            "config": self.config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DatasetVersion(Base):
    """An immutable snapshot of a dataset (v1 = the uploaded file, then v2, v3 ...).

    Every cleaning/transformation operation writes a *new* version file, so the
    original data is never destroyed and any analysis can be reproduced against the
    exact version it used.
    """

    __tablename__ = "dataset_versions"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)  # 1, 2, 3 ...
    parent_version = Column(Integer, nullable=True)
    storage_path = Column(String(500), nullable=False)
    file_format = Column(String(20), nullable=False, default="parquet")  # parquet|csv
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    is_current = Column(Integer, default=1)  # 1 for the newest version
    label = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="versions")
    operations = relationship(
        "DatasetOperation",
        back_populates="resulting_version",
        cascade="all, delete-orphan",
        order_by="DatasetOperation.sequence",
    )

    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),
    )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "dataset_id": self.dataset_id,
            "parent_version": self.parent_version,
            "file_format": self.file_format,
            "row_count": self.row_count or 0,
            "column_count": self.column_count or 0,
            "is_current": bool(self.is_current),
            "label": self.label,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DatasetOperation(Base):
    """Audit trail entry: one cleaning/transformation step that produced a version."""

    __tablename__ = "dataset_operations"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id = Column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence = Column(Integer, nullable=False)  # 1, 2, 3 ... within the dataset
    operation_group = Column(String(20), nullable=False)  # clean | transform
    operation_type = Column(String(50), nullable=False)
    configuration = Column(JSON, nullable=False)
    source_version = Column(Integer, nullable=False)
    result_version = Column(Integer, nullable=False)
    summary = Column(JSON, nullable=True)
    warnings = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="operations")
    resulting_version = relationship("DatasetVersion", back_populates="operations")

    def to_dict(self) -> dict:
        """Matches the documented history shape: version / type / configuration."""
        return {
            "sequence": self.sequence,
            "version": self.result_version,
            "type": self.operation_type,
            "group": self.operation_group,
            "configuration": self.configuration or {},
            "source_version": self.source_version,
            "summary": self.summary or {},
            "warnings": self.warnings or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AnalysisRun(Base):
    """A statistical analysis executed against one dataset version (MVP-19 engine)."""

    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version = Column(Integer, nullable=False)
    analysis_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="success")
    parameters = Column(JSON, nullable=True)
    result = Column(JSON, nullable=False)  # the standard result structure
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="analysis_runs")

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "analysis_type": self.analysis_type,
            "status": self.status,
            "parameters": self.parameters or {},
            "result": self.result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ExportedReport(Base):
    __tablename__ = "exported_reports"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_format = Column(String(10), nullable=False)  # pdf, xlsx
    storage_path = Column(String(500), nullable=False, default="")
    # Additions to schema.sql: an async export needs a status + error trail.
    status = Column(String(20), default="processing")  # processing|completed|failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="reports")
    user = relationship("User", back_populates="reports")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "user_id": self.user_id,
            "file_format": self.file_format,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

