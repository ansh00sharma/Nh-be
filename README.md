# TaskFlow Backend

TaskFlow is a Django REST Framework backend for a small task-management POC.

It includes:
- JWT authentication
- Minimal manager/agent RBAC
- Project CRUD
- Task CRUD
- Task filtering and pagination
- Redis-backed task-list caching
- Celery background jobs
- Overdue task notifications
- Task reassignment notifications
- Notification listing
- Health endpoint
- Metrics endpoint

All JSON API responses use:

```json
{
  "message": "Human readable message",
  "data": {},
  "status": "success",
  "status_code": 200
}
```

Errors use the same envelope with `"status": "error"` and `data: null`.

## RBAC Assumption

The original assignment defines project ownership and task assignees, but does
not define formal roles. For this POC, TaskFlow interprets those concepts as:

- Manager: the project owner who manages their own projects and the tasks in
  those projects.
- Agent: the task assignee who works on assigned tasks and can update task
  status.

Roles are stored with Django Groups named `manager` and `agent`. Public signup
always creates an `agent`; managers can be assigned through Django admin or a
future seed command.

## Requirements

- Python 3.12
- PostgreSQL
- Redis
- Docker and Docker Compose, optional for local setup

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `.env` with local PostgreSQL and Redis values, then run:

```bash
python manage.py migrate
python manage.py runserver
```

Run Django checks and tests:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Run Celery worker:

```bash
celery -A config worker --loglevel=info
```

Run Celery Beat:

```bash
celery -A config beat --loglevel=info
```

## Docker Setup

Build the backend image:

```bash
docker build -t taskflow-backend:local .
```

Inspect the built image:

```bash
docker images taskflow-backend:local
```

Run a Django check against the image:

```bash
docker run --rm --env-file .env taskflow-backend:local python manage.py check
```

If your `.env` points `POSTGRES_HOST=localhost`, prefer the Compose check below because containers should use the Compose service name `postgres`.

## Docker Compose

Services:
- `web`
- `postgres`
- `redis`
- `celery_worker`
- `celery_beat`

Build:

```bash
docker compose build
```

If your machine uses Docker Compose v1, use `docker-compose` in place of `docker compose`.

Start PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
```

Run migrations:

```bash
docker compose run --rm web python manage.py migrate
```

Start everything:

```bash
docker compose up -d
```

Show running containers:

```bash
docker compose ps
```

Check logs:

```bash
docker compose logs web
docker compose logs celery_worker
docker compose logs celery_beat
```

Test health:

```bash
curl http://localhost:8000/api/health/
```

Expected shape:

```json
{
  "message": "Service is healthy",
  "data": {
    "database": "healthy",
    "redis": "healthy"
  },
  "status": "success",
  "status_code": 200
}
```

Test metrics:

```bash
curl http://localhost:8000/api/metrics/
```

Stop containers:

```bash
docker compose down
```

Remove containers and local PostgreSQL Docker volume:

```bash
docker compose down -v
```

`-v` deletes locally persisted PostgreSQL data.

## Useful Pre-Push Docker Verification

```bash
docker compose down
docker compose build --no-cache
docker compose up -d postgres redis
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py test
docker compose up -d
docker compose ps
curl http://localhost:8000/api/health/
```

This confirms:
- Image builds
- PostgreSQL connects
- Redis connects
- Migrations work
- Django checks pass
- Tests pass
- Web container starts
- Health endpoint works
- Celery worker starts
- Celery Beat starts

## API Summary

Protected endpoints require:

```text
Authorization: Bearer <access_token>
```

Authentication:
- `POST /api/auth/signup/`
- `POST /api/auth/login/`
- `POST /api/auth/token/refresh/`
- `GET /api/auth/me/`

Projects:
- `POST /api/projects/`
- `GET /api/projects/`
- `GET /api/projects/{id}/`
- `PUT /api/projects/{id}/`
- `PATCH /api/projects/{id}/`
- `DELETE /api/projects/{id}/`

Tasks:
- `POST /api/tasks/`
- `GET /api/tasks/`
- `GET /api/tasks/{id}/`
- `PUT /api/tasks/{id}/`
- `PATCH /api/tasks/{id}/`
- `DELETE /api/tasks/{id}/`

Supported task filters:

```text
/api/tasks/?status=todo
/api/tasks/?status=in_progress
/api/tasks/?status=done
/api/tasks/?assignee=2
/api/tasks/?project=1
/api/tasks/?due_date_from=2026-09-20&due_date_to=2026-09-30
```

Pagination:

```text
/api/tasks/?page=2
/api/tasks/?page_size=10
```

Notifications:
- `GET /api/notifications/`

Health and metrics:
- `GET /api/health/`
- `GET /api/metrics/`

## Architecture Notes

DRF was selected for conventional API development. JWT works well with a separate React frontend. PostgreSQL stores application data. Redis provides task-list caching and Celery infrastructure. User/version-based cache invalidation prevents stale task-list reads. Celery keeps notification processing outside the request-response cycle.

## Deployment Notes

A reasonable production setup would include:
- Nginx
- Gunicorn/Django container
- PostgreSQL
- Redis
- Celery worker
- Celery Beat
