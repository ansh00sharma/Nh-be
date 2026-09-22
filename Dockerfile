FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app


# System dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*


# Install Python dependencies first for Docker layer caching
COPY requirements.txt .

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# Copy application
COPY . .


EXPOSE 8000


CMD [
    "gunicorn",
    "taskflow.wsgi:application",
    "--bind",
    "0.0.0.0:8000",
    "--workers",
    "3",
    "--timeout",
    "120"
]