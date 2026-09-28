from datetime import datetime, timezone
import logging
import sys

from fastapi import HTTPException

from app.models.task import Task, TaskStatus
from app.models.user import USERS, Role, User
from app.store import connection


logger = logging.getLogger("task_management.notifications")
if not logger.handlers:
    logger.addHandler(logging.StreamHandler(sys.stdout))
logger.setLevel(logging.INFO)


def require_role(user: User, role: Role):
    if user.role != role:
        raise HTTPException(status_code=403, detail=f"Requires role {role.value}")


def find_task(db, task_id: int) -> Task:
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return Task(**dict(row))


def create(database, user, data):
    require_role(user, Role.SUPERVISOR)
    with connection(database, write=True) as db:
        cursor = db.execute(
            "INSERT INTO tasks (title, description, status) VALUES (?, ?, ?)",
            (data.title, data.description, TaskStatus.CREATED.value),
        )
        return find_task(db, cursor.lastrowid)


def list_tasks(database, user):
    with connection(database) as db:
        if user.role == Role.SUPERVISOR:
            rows = db.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM tasks WHERE assigned_to = ? ORDER BY id", (user.id,)
            ).fetchall()
        return [Task(**dict(row)) for row in rows]


def assign(database, user, task_id, worker_id):
    require_role(user, Role.SUPERVISOR)
    with connection(database, write=True) as db:
        task = find_task(db, task_id)
        worker = USERS.get(worker_id)
        if worker is None:
            raise HTTPException(status_code=404, detail="Worker not found")
        if worker.role != Role.WORKER:
            raise HTTPException(status_code=400, detail="Assignee must be a worker")
        if task.status != TaskStatus.CREATED:
            raise HTTPException(status_code=400, detail="Only CREATED tasks can be assigned")
        message = f"Task {task_id} assigned to worker {worker_id}"
        db.execute(
            "UPDATE tasks SET assigned_to = ?, status = ? WHERE id = ?",
            (worker_id, TaskStatus.ASSIGNED.value, task_id),
        )
        db.execute(
            "INSERT INTO notifications (user_id, task_id, message, created_at) VALUES (?, ?, ?, ?)",
            (worker_id, task_id, message, datetime.now(timezone.utc).isoformat()),
        )
        result = find_task(db, task_id)
    # Log only after both writes have committed successfully.
    logger.info(message)
    return result


def update_status(database, user, task_id, status):
    require_role(user, Role.WORKER)
    with connection(database, write=True) as db:
        task = find_task(db, task_id)
        if task.assigned_to != user.id:
            raise HTTPException(status_code=403, detail="Task is not assigned to this worker")
        next_status = {
            TaskStatus.ASSIGNED: TaskStatus.IN_PROGRESS,
            TaskStatus.IN_PROGRESS: TaskStatus.COMPLETED,
        }.get(task.status)
        if status != next_status:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid transition: {task.status.value} -> {status.value}",
            )
        db.execute("UPDATE tasks SET status = ? WHERE id = ?", (status.value, task_id))
        return find_task(db, task_id)


def list_notifications(database, user):
    require_role(user, Role.WORKER)
    with connection(database) as db:
        rows = db.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY id", (user.id,)
        ).fetchall()
        return [dict(row) for row in rows]
