from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_current_user
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskAssign, TaskCreate, TaskStatusUpdate
from app.services import tasks


router = APIRouter(prefix="/tasks", tags=["tasks"])
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=list[Task])
def get_tasks(request: Request, user: CurrentUser):
    return tasks.list_tasks(request.app.state.database_path, user)


@router.post("", response_model=Task, status_code=201)
def create_task(task_data: TaskCreate, request: Request, user: CurrentUser):
    return tasks.create(request.app.state.database_path, user, task_data)


@router.post("/{task_id}/assign", response_model=Task)
def assign_task(task_id: int, data: TaskAssign, request: Request, user: CurrentUser):
    return tasks.assign(request.app.state.database_path, user, task_id, data.user_id)


@router.patch("/{task_id}/status", response_model=Task)
def update_task_status(task_id: int, data: TaskStatusUpdate, request: Request, user: CurrentUser):
    return tasks.update_status(request.app.state.database_path, user, task_id, data.status)
