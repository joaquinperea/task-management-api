from enum import Enum
from pydantic import BaseModel


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class Task(BaseModel):
    id: int
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.CREATED
    assigned_to: str | None = None
