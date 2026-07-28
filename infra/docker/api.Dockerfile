FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /srv
COPY apps/api/pyproject.toml apps/api/uv.lock* /srv/
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY apps/api /srv
COPY infra/migrations /srv/infra/migrations
COPY database/schema.sql /srv/database/schema.sql

ENV PATH="/srv/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
