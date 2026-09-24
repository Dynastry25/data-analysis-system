# StatFlow backend — FastAPI + pandas/Polars engine
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed at build time only (no compiler needed for pinned wheels).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Static user-uploaded files are kept on a named volume.
RUN mkdir -p /data

ENV DATABASE_URL=sqlite:////data/statflow.db \
    STORAGE_DIR=/data/storage \
    SECRET_KEY=CHANGE_ME_IN_PRODUCTION \
    FRONTEND_ORIGIN=http://localhost:3000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]