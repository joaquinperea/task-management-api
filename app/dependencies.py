from typing import Annotated

from fastapi import Header, HTTPException

from app.models.user import USERS, User


def get_current_user(x_user_id: Annotated[str, Header(alias="X-User-Id")]) -> User:
    user = USERS.get(x_user_id)
    if user is None:
        raise HTTPException(status_code=403, detail="Unknown user")
    return user
