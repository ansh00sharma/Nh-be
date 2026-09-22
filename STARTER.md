# Backend Starter Guide

This guide explains how to run the TaskFlow backend locally for development.

## Requirements

- Python 3.12
- PostgreSQL
- Redis
- Git
- Optional: Docker, if you want to run PostgreSQL/Redis locally in containers

## 1. Open The Backend Repo

```bash
cd /home/ansh/ansh/nh/Nh-be
```

## 2. Create A Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

## 3. Install Python Requirements

```bash
pip install -r requirements.txt
```

This includes the Swagger/OpenAPI dependency:

```text
drf-spectacular
```

## 4. Create The Local `.env` File

```bash
cp .env.example .env
```

Edit `.env` with your local values.

Example local configuration:

```env
SECRET_KEY=change-me-local-dev-key
DEBUG=True

POSTGRES_DB=taskflow
POSTGRES_USER=taskflow
POSTGRES_PASSWORD=taskflow
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

REDIS_URL=redis://localhost:6379/0

CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=no-reply@taskflow.local
```

For local development, `django.core.mail.backends.console.EmailBackend` prints emails to the terminal instead of sending real email.

## 5. Start PostgreSQL

Use an existing local PostgreSQL server, or start one with Docker:

```bash
docker run --name taskflow-postgres \
  -e POSTGRES_DB=taskflow \
  -e POSTGRES_USER=taskflow \
  -e POSTGRES_PASSWORD=taskflow \
  -p 5432:5432 \
  -d postgres:16-alpine
```

If the container already exists:

```bash
docker start taskflow-postgres
```

Your `.env` database values must match the database, username, password, host, and port you use here.

## 6. Start Redis

Use an existing local Redis server, or start one with Docker:

```bash
docker run --name taskflow-redis \
  -p 6379:6379 \
  -d redis:7-alpine
```

If the container already exists:

```bash
docker start taskflow-redis
```

Your `.env` should contain:

```env
REDIS_URL=redis://localhost:6379/0
```

## 7. Run Django Checks

```bash
python manage.py check
```

## 8. Run Database Migrations

```bash
python manage.py migrate
```

Migrations create the database schema and currently seed initial TaskFlow roles, demo users, and demo projects. Review seed data before using this project outside local development.

## 9. Create A Superuser

Optional, but useful for Django admin:

```bash
python manage.py createsuperuser
```

The project uses email as the login field.

## 10. Start The API Server

```bash
python manage.py runserver
```

The API will run at:

```text
http://127.0.0.1:8000/
```

Useful checks:

```bash
curl http://127.0.0.1:8000/api/health/
curl http://127.0.0.1:8000/api/metrics/
```

Swagger/OpenAPI docs:

```text
http://127.0.0.1:8000/api/docs/
http://127.0.0.1:8000/api/redoc/
http://127.0.0.1:8000/api/schema/
```

To test protected endpoints in Swagger UI:

1. Log in at `POST /api/auth/login/`.
2. Copy the returned access token.
3. Click `Authorize` in Swagger UI.
4. Enter `Bearer <access-token>`.

## 11. Run The Celery Worker

Open a second terminal:

```bash
cd /home/ansh/ansh/nh/Nh-be
source .venv/bin/activate
celery -A config worker --loglevel=info
```

The worker processes async notification jobs, including task-created, task-reassigned, task-status-changed, and overdue-task email jobs.

## 12. Run Celery Beat

Open a third terminal:

```bash
cd /home/ansh/ansh/nh/Nh-be
source .venv/bin/activate
celery -A config beat --loglevel=info
```

Celery Beat schedules periodic jobs. The current schedule runs overdue-task notification checks every 60 seconds.

## 13. Local Process Checklist

For full local development, keep these processes running:

- PostgreSQL
- Redis
- Django API server
- Celery worker
- Celery Beat

## 14. Common API Flow

Sign up:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Local",
    "last_name": "User",
    "email": "local@example.com",
    "password": "strong-password-123"
  }'
```

Log in:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "local@example.com",
    "password": "strong-password-123"
  }'
```

Use the returned access token:

```bash
curl http://127.0.0.1:8000/api/auth/me/ \
  -H "Authorization: Bearer <access-token>"
```

## 15. Run Tests

```bash
python manage.py test
```

## 16. Check For Pending Migrations

```bash
python manage.py makemigrations --check --dry-run
```

## 17. Validate The OpenAPI Schema

```bash
python manage.py spectacular --validate --file schema.yml
```

This writes the generated OpenAPI schema to `schema.yml` and validates it.

## 18. Stop Local Docker Dependencies

If you started PostgreSQL and Redis using Docker:

```bash
docker stop taskflow-postgres taskflow-redis
```

To remove the containers and local data:

```bash
docker rm taskflow-postgres taskflow-redis
```

Removing `taskflow-postgres` deletes the local database stored inside that container.

## Troubleshooting

### Missing Environment Variable

If Django raises `Missing required environment variable`, check that `.env` exists and contains all required values.

### Database Connection Failed

Check:

- PostgreSQL is running.
- `.env` database values are correct.
- The database exists.
- The user has the correct password and permissions.

### Redis Connection Failed

Check:

- Redis is running.
- `REDIS_URL` is correct.
- Nothing else is blocking port `6379`.

### Celery Jobs Are Not Running

Check:

- Redis is running.
- Celery worker is running.
- Celery Beat is running for scheduled jobs.
- All terminals are using the same virtual environment and `.env` file.

### Frontend Cannot Call Backend

Check:

- Backend server is running on port `8000`.
- Frontend `VITE_API_BASE_URL` points to `http://localhost:8000`.
- `CORS_ALLOWED_ORIGINS` includes the frontend origin, usually `http://localhost:5173`.
