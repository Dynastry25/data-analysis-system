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
    cleaning_actions = relationship(
        "CleaningAction",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="CleaningAction.id",
    )
    analysis_results = relationship(
        "AnalysisResult",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="AnalysisResult.id",
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


class CleaningAction(Base):
    __tablename__ = "cleaning_actions"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type = Column(String(50), nullable=False)
    parameters = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="cleaning_actions")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "action_type": self.action_type,
            "parameters": self.parameters or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_type = Column(String(50), nullable=False)
    result_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="analysis_results")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "analysis_type": self.analysis_type,
            "result_data": self.result_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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

