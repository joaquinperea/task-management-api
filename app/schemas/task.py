from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models.task import TaskStatus


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: NonEmptyString
    description: str | None = None


class TaskAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: NonEmptyString


class TaskStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: TaskStatus
