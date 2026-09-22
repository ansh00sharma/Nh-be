# =========================================================
# Stage 1: Builder
# =========================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Packages required only to BUILD Python dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Create isolated virtual environment
RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# =========================================================
# Stage 2: Runtime
# =========================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime dependency for PostgreSQL client libraries
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source
COPY . .

RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]

CMD [
    "gunicorn",
    "config.wsgi:application",
    "--bind",
    "0.0.0.0:8000",
    "--workers",
    "3",
    "--timeout",
    "120"
]