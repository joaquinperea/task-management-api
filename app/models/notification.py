from datetime import datetime

from pydantic import BaseModel


class Notification(BaseModel):
    id: int
    user_id: str
    task_id: int
    message: str
    created_at: datetime
