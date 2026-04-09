FROM python:3.11.9 AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app


RUN python -m venv .venv
COPY requirements.txt ./
RUN .venv/bin/pip install -r requirements.txt
FROM python:3.11.9-slim
WORKDIR /app
COPY --from=builder /app/.venv .venv/
COPY . .
# Bind all interfaces so Fly's proxy can reach the app (not 127.0.0.1-only).
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
