# ─────────────────────────────────────────────────────────────────────────────
# IMPT API + Worker image (Python 3.12)
# Used for all three compose services: api, worker, beat.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── System packages ───────────────────────────────────────────────────────────
# curl  — health check probe
# docker.io — worker needs the Docker CLI to launch sandbox containers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first so Docker layer cache is reused on code-only changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN useradd -m -u 1001 imptuser \
    && chown -R imptuser:imptuser /app
USER imptuser

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000
ENV PYTHONPATH=/app

# Default: run the API server (overridden by docker-compose for worker/beat)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
