FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/apps/api/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.8.22

WORKDIR /app/apps/api
COPY apps/api/ ./
RUN uv sync --locked --no-dev

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
