# TaskFlow Backend

TaskFlow Backend is a Django REST Framework API for a role-based task management product. It powers authentication, user management, project ownership, task assignment, dashboard access, notifications, health checks, metrics, Redis-backed caching, and asynchronous email workflows.

The backend is designed for a frontend client that consumes JWT-protected APIs and displays different modules depending on the logged-in user's role.

## Live Links

- Live application: http://15.252.221.30/
- Swagger API docs: http://15.252.221.30/api/docs/
- Grafana: http://15.252.221.30:3000/
- Prometheus: http://15.252.221.30:9090/

## Core Functionality

- User signup, login, logout, token refresh, and current-user profile APIs.
- Role-based access control using Django groups.
- Admin and manager user-management APIs.
- Project CRUD for admins and managers.
- Task CRUD with role-specific visibility and permissions.
- Task filters by status, assignee, project, and due-date range.
- Redis-backed caching for task list responses.
- Notification records for task events.
- Email notification delivery through Django's email backend.
- Celery worker tasks for async notifications.
- Celery Beat schedule for overdue-task notification scans.
- API health checks for PostgreSQL and Redis.
- Simple in-memory request metrics.
- Standard JSON response envelope for API consistency.
- Swagger UI, ReDoc, and OpenAPI schema generation.

## Main Modules

### `config`

Project configuration for Django, URL routing, WSGI/ASGI, Celery, installed apps, database, Redis cache, CORS, email, JWT, and REST Framework settings.

Important files:

- `config/settings.py`
- `config/urls.py`
- `config/celery.py`

### `api`

Shared API infrastructure used across the project.

Responsibilities:

- Standard success/error response shape.
- Standard JSON renderer.
- DRF exception formatting.
- Pagination defaults.
- Health endpoint.
- Metrics endpoint.
- Metrics middleware.
- OpenAPI schema exposure through `drf-spectacular`.

Response shape:

```json
{
  "message": "Request successful",
  "data": {},
  "status": "success",
  "status_code": 200
}
```

Errors use the same shape with `"status": "error"` and `"data": null`.

### `users`

Custom user model and authentication module.

Responsibilities:

- Email-based custom user model.
- Signup and login.
- JWT token generation through Simple JWT.
- Logout with refresh-token blacklist support.
- Current-user profile endpoint.
- Admin/manager managed-user CRUD.
- Role assignment through Django groups.

Roles:

- `admin`
- `manager`
- `agent`

Module access:

- Admin: `dashboard`, `users`, `projects`, `tasks`
- Manager: `users`, `projects`, `tasks`
- Agent: `tasks`

### `projects`

Project management module.

Responsibilities:

- Create, list, retrieve, update, and delete projects.
- Store project ownership through the `owner` user relation.
- Restrict access by role.

Access rules:

- Admins can access all projects.
- Managers can access only their own projects.
- Agents cannot access project CRUD directly.

### `tasks`

Task management module.

Responsibilities:

- Create, list, retrieve, update, and delete tasks.
- Assign tasks to users.
- Track task status.
- Store due dates.
- Filter task lists.
- Cache task list responses per user, role, cache version, and query string.
- Invalidate task-list cache versions when task/project changes affect visible data.
- Dispatch notification jobs when tasks are created, reassigned, or status changes.

Task statuses:

- `todo`
- `in_progress`
- `done`

Access rules:

- Admins can access all tasks.
- Managers can access tasks under projects they own.
- Agents can access tasks assigned to them.
- Admins and managers can create and delete tasks.
- Agents can update task status, but cannot change project, assignee, title, description, or due date.

### `notifications`

Notification and email module.

Responsibilities:

- Store task notifications.
- List notifications for the authenticated user.
- Send task-related emails.
- Mark whether a notification has been sent.
- Periodically scan overdue tasks through Celery Beat.

Notification types:

- `task_created`
- `task_overdue`
- `task_reassigned`
- `task_status_changed`

Email templates live in `templates/emails/`.

### `dashboard`

Admin-only dashboard placeholder module.

Current behavior:

- Provides an authenticated dashboard endpoint.
- Allows access only for admins.
- Returns placeholder dashboard data until real analytics are implemented.

## Database

The project uses PostgreSQL as the primary relational database.

Main data entities:

- `users.User`: custom user table using email as the login identifier.
- `auth.Group`: stores TaskFlow roles: `admin`, `manager`, and `agent`.
- `projects.Project`: project records owned by users.
- `tasks.Task`: task records connected to projects and optional assignees.
- `notifications.Notification`: task-event notifications connected to users and tasks.
- Simple JWT blacklist tables: store blacklisted refresh tokens for logout.
- Django built-in tables: sessions, permissions, content types, admin logs, and migrations.

Important relationships:

- A user can own many projects.
- A project belongs to one owner.
- A project can have many tasks.
- A task belongs to one project.
- A task may be assigned to one user.
- A user can have many assigned tasks.
- A user can have many notifications.
- A notification belongs to one task and one user.

## Redis

Redis is used for two backend responsibilities:

- Django cache backend for task-list caching and health checks.
- Celery broker/result backend for background jobs.

The `REDIS_URL` environment variable is shared by both Django cache and Celery.

## Business Logic

TaskFlow is structured around three operating roles.

Admins supervise the whole system. They can see all projects and tasks, access the dashboard, manage users, and perform project/task operations according to API permissions.

Managers own projects. They create projects, create tasks inside their own projects, assign tasks to agents, track work, and receive status-change notifications for their project tasks.

Agents execute assigned work. They see only their own tasks and can move those tasks through statuses without being allowed to change ownership, assignment, title, description, project, or due date.

Expected task lifecycle:

1. An admin or manager creates a project.
2. An admin or manager creates a task under an accessible project.
3. The task may be assigned to an agent.
4. A task-created notification is stored and emailed to the assignee.
5. If the task is reassigned, the new assignee receives a reassignment notification.
6. The assignee updates task status as work progresses.
7. Status changes notify the project owner.
8. Celery Beat periodically checks for overdue incomplete tasks.
9. Overdue notifications are stored and emailed to the assignee.
10. Task-list cache entries are invalidated when changes affect visible task data.

## API Surface

Base endpoints:

- `GET /` and `GET /api/`
- `GET /api/schema/`
- `GET /api/docs/`
- `GET /api/redoc/`
- `GET /api/health/`
- `GET /api/metrics/`

Authentication:

- `POST /api/auth/signup/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `POST /api/auth/token/refresh/`
- `GET /api/auth/me/`

Application modules:

- `/api/dashboard/`
- `/api/users/`
- `/api/projects/`
- `/api/tasks/`
- `/api/notifications/`

Most module endpoints require:

```http
Authorization: Bearer <access-token>
```

## API Documentation

Swagger/OpenAPI documentation is generated with `drf-spectacular`.

Documentation endpoints:

- `GET /api/schema/`: raw OpenAPI schema.
- `GET /api/docs/`: Swagger UI for browser-based API testing.
- `GET /api/redoc/`: ReDoc API reference.

Live Swagger URL: http://15.252.221.30/api/docs/

For protected endpoints, log in through `POST /api/auth/login/`, copy the returned access token, open `/api/docs/`, click `Authorize`, and enter:

```text
Bearer <access-token>
```

## Background Jobs

Celery tasks are defined in `notifications/tasks.py`.

Current jobs:

- Create task-created notifications.
- Create task-reassigned notifications.
- Create task-status-changed notifications.
- Scan overdue tasks and send overdue notifications.

Celery Beat schedule:

- `create_overdue_task_notifications` runs every 60 seconds.

## Environment Variables

The backend reads environment values from `.env` automatically during local development.

Required core values:

- `SECRET_KEY`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `REDIS_URL`

Common optional values:

- `DEBUG`
- `CORS_ALLOWED_ORIGINS`
- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_USE_TLS`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`

See `STARTER.md` for local setup commands.

## Production Notes

- Replace all development secrets before deployment.
- Review and remove demo seed credentials before production use.
- Set a production-safe `SECRET_KEY`.
- Restrict `ALLOWED_HOSTS`; it is currently permissive in code.
- Set `DEBUG=False`.
- Configure production `CORS_ALLOWED_ORIGINS`.
- Use managed PostgreSQL and Redis where possible.
- Run Celery worker and Celery Beat as separate long-running processes.
