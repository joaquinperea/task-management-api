from enum import Enum

from pydantic import BaseModel


class Role(str, Enum):
    SUPERVISOR = "SUPERVISOR"
    WORKER = "WORKER"


class User(BaseModel):
    id: str
    name: str
    role: Role


USERS = {
    "1": User(id="1", name="Supervisor", role=Role.SUPERVISOR),
    "2": User(id="2", name="Worker One", role=Role.WORKER),
    "3": User(id="3", name="Worker Two", role=Role.WORKER),
}
