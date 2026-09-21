"""FastAPI application entrypoint for the Data Analysis Platform MVP."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_PREFIX, CORS_ORIGINS, MAX_UPLOAD_SIZE_BYTES
from app.database import Base, engine

# `app.routers.*` imports the SQLAlchemy models, which registers every table from
# schema.sql on ``Base.metadata`` before the lifespan below creates them.
from app.routers import analysis, auth, charts, cleaning, datasets, reports


@asynccontextmanager
async def lifespan(_: FastAPI):
    # SQLite/dev convenience: create tables on startup. In production run the SQL
    # from schema.sql (or Alembic migrations) against PostgreSQL instead.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Data Analysis Platform API",
    description=(
        "MVP API: upload CSV/XLSX data, clean it, run descriptive statistics, "
        "correlation, regression and hypothesis tests, build charts and export reports."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    datasets.router,
    cleaning.router,
    analysis.router,
    charts.router,
    reports.router,
):
    app.include_router(router, prefix=API_PREFIX)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "Data Analysis Platform API",
        "version": "0.1.0",
        "docs": "/docs",
        "api_prefix": API_PREFIX,
    }


@app.get(f"{API_PREFIX}/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "max_upload_mb": MAX_UPLOAD_SIZE_BYTES // (1024 * 1024),
    }
