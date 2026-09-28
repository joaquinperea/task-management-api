from contextlib import asynccontextmanager
import os

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.routers.tasks import router as tasks_router
from app.services.tasks import list_notifications
from app.store import DEFAULT_DATABASE, initialize


def create_app(database_path=None):
    @asynccontextmanager
    async def lifespan(application):
        initialize(application.state.database_path)
        yield

    application = FastAPI(title="Task Management API", version="1.0.0", lifespan=lifespan)
    application.state.database_path = (
        database_path if database_path is not None
        else os.environ.get("TASK_DATABASE_PATH", str(DEFAULT_DATABASE))
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc):
        return JSONResponse(status_code=400, content=jsonable_encoder({"detail": exc.errors()}))

    application.include_router(tasks_router)

    @application.get("/health", tags=["health"])
    def health_check():
        return {"status": "ok"}

    @application.get("/notifications", response_model=list[Notification], tags=["notifications"])
    def get_notifications(request: Request, user: User = Depends(get_current_user)):
        return list_notifications(request.app.state.database_path, user)

    # FastAPI documents validation as 422 by default; this assessment requires 400.
    default_openapi = application.openapi

    def custom_openapi():
        schema = default_openapi()
        for path in schema["paths"].values():
            for operation in path.values():
                responses = operation.get("responses", {})
                if "422" in responses:
                    responses["400"] = responses.pop("422")
                if any(p.get("name") == "X-User-Id" for p in operation.get("parameters", [])):
                    responses["403"] = {"description": "Unknown user, forbidden role or ownership"}
                if any(p.get("name") == "task_id" for p in operation.get("parameters", [])):
                    responses["404"] = {"description": "Task or worker not found"}
        return schema

    application.openapi = custom_openapi
    return application


app = create_app()
