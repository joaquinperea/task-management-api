# Task Management API

A REST API for creating, assigning, and tracking tasks through a forward-only
lifecycle. Built with Python 3.12+, FastAPI, Pydantic, and SQLite. No external
services are required.

## Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

For runtime dependencies only, install `requirements.txt` instead.

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json
- Health check: http://127.0.0.1:8000/health

## Tests

```bash
source .venv/bin/activate
python -m pytest -q
```

Tests use isolated temporary databases. They cover authorization, ownership,
valid and invalid transitions, request validation, notification creation,
persistence across restarts, transaction rollback, concurrent assignments,
SQL-like input handling, and the OpenAPI contract.

## Seed users and caller identification

The following users are defined in `app/models/user.py` and available at startup:

| ID | Name | Role |
| --- | --- | --- |
| 1 | Supervisor | SUPERVISOR |
| 2 | Worker One | WORKER |
| 3 | Worker Two | WORKER |

Include `X-User-Id` in task and notification requests. For example,
`X-User-Id: 1` identifies the supervisor. User IDs are strings; use
`{"user_id":"2"}` in assignment requests.

The header provides caller identification only, as required by the exercise.
It does not authenticate the caller. Signup, passwords, and tokens are out of scope.

## Endpoints

| Method | Path | Access and behavior |
| --- | --- | --- |
| POST | `/tasks` | Supervisor creates a task in CREATED; returns 201 |
| GET | `/tasks` | Supervisor lists all tasks; worker lists only assigned tasks |
| POST | `/tasks/{id}/assign` | Supervisor assigns a task to a worker |
| PATCH | `/tasks/{id}/status` | Assigned worker advances the task status |
| GET | `/notifications` | Worker lists their own notification records |
| GET | `/health` | Public application health check |

Successful operations return 200 unless otherwise specified.

### Lifecycle and assignment

```text
CREATED -> ASSIGNED -> IN_PROGRESS -> COMPLETED
```

- New tasks start in CREATED without an assignee.
- Only supervisors can create and assign tasks.
- Assignment sets the worker and moves the task to ASSIGNED.
- Only the assigned worker can advance it to IN_PROGRESS and then COMPLETED.
- Assignment saves a notification with `user_id`, `task_id`, `message`, and a UTC
  `created_at` timestamp, and logs the message to stdout after the transaction commits.

The lifecycle diagram is interpreted as consecutive transitions: skipping,
reversing, or repeating a status is rejected. Assignment is allowed only from
CREATED; reassignment, including to the same worker, is rejected. These choices
avoid resetting progress or creating duplicate assignment notifications.

### Validation and errors

Error responses contain a `detail` field.

| Status | Meaning |
| --- | --- |
| 400 | Invalid request data, missing header, invalid transition, or non-worker assignee |
| 403 | Unknown caller, forbidden role, or task not owned by the caller |
| 404 | Task or assignment target does not exist |

Titles must contain non-whitespace characters. Extra request fields are rejected.
The server controls task IDs and initial status. Request validation returns 400
instead of FastAPI's default 422 to match the assessment's HTTP contract; OpenAPI
reflects this behavior.

## Example workflow

The examples assume a new database, where the first task has ID 1. Otherwise,
replace `1` in the task URLs with the ID returned by the creation request.

```bash
# Create a task as the supervisor.
curl -i -X POST http://127.0.0.1:8000/tasks \
  -H 'X-User-Id: 1' -H 'Content-Type: application/json' \
  -d '{"title":"Fix login bug","description":"Login returns 500"}'

# Assign it to Worker One.
curl -i -X POST http://127.0.0.1:8000/tasks/1/assign \
  -H 'X-User-Id: 1' -H 'Content-Type: application/json' \
  -d '{"user_id":"2"}'

# List Worker One's tasks.
curl -i http://127.0.0.1:8000/tasks -H 'X-User-Id: 2'

# Start the task as Worker One.
curl -i -X PATCH http://127.0.0.1:8000/tasks/1/status \
  -H 'X-User-Id: 2' -H 'Content-Type: application/json' \
  -d '{"status":"IN_PROGRESS"}'

# Complete the task as Worker One.
curl -i -X PATCH http://127.0.0.1:8000/tasks/1/status \
  -H 'X-User-Id: 2' -H 'Content-Type: application/json' \
  -d '{"status":"COMPLETED"}'

# Read Worker One's saved notifications.
curl -i http://127.0.0.1:8000/notifications -H 'X-User-Id: 2'
```

Attempting the status update with `X-User-Id: 3` returns 403. Moving a completed
task back to IN_PROGRESS as Worker One returns 400. Worker Two's task list is
empty until a task is assigned to that user.

In Swagger UI, select **Try it out**, enter `X-User-Id`, the path parameters and
request body, and select **Execute**.

## Project structure

```text
app/
  main.py                 Application factory, startup, and error handling
  dependencies.py         Header-based caller lookup
  models/                 Task, status, user, role, and notification models
  schemas/                Request validation models
  routers/tasks.py        Task HTTP endpoints
  services/tasks.py       Authorization and lifecycle rules
  store.py                SQLite connections and schema initialization
tests/test_api.py          API and persistence tests
```

Request schemas are separate from stored task models so clients can only supply
fields supported by each operation. The service centralizes business rules;
routers handle HTTP inputs and responses. Services use FastAPI HTTP exceptions
to keep the implementation small.

## Persistence and concurrency

SQLite stores tasks and notifications in `tasks.db` at the repository root. The
file is excluded from Git. Set `TASK_DATABASE_PATH` to use another database file;
its parent directory must already exist. The schema is initialized at startup.

Each operation opens its own connection. Write operations use `BEGIN IMMEDIATE`
to serialize competing read-check-write sequences. Assignment and notification
creation share one transaction: both commit or both roll back. Task IDs are
allocated by SQLite.

All SQL statements are fixed strings. Request-derived values are passed separately
through SQLite `?` placeholders, rather than interpolated into SQL text. Schema
initialization uses a static script with no request input.

The stdout log is emitted after commit. Unlike the database record, console
logging is not atomic with the transaction: a process failure immediately after
commit could prevent that message from being printed.

## Scope and possible improvements

This implementation includes the required task operations plus health,
notification listing, and OpenAPI documentation. It does not include a frontend,
external notification delivery, pagination, or authentication.

Potential extensions include versioned schema migrations, PostgreSQL for higher
write concurrency, and domain-specific exceptions if services gain non-HTTP
consumers. External notification delivery would benefit from a transactional
outbox. Real authentication would be necessary before deployment to an untrusted
network.
