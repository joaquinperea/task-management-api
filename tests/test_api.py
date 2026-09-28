from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.main import create_app


def headers(user="1"):
    return {"X-User-Id": user}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as c:
        yield c


def create(client):
    response = client.post("/tasks", headers=headers(), json={"title": "Test task"})
    assert response.status_code == 201
    return response.json()["id"]


def assign(client, task_id, worker="2"):
    return client.post(f"/tasks/{task_id}/assign", headers=headers(), json={"user_id": worker})


def change(client, task_id, status, user="2"):
    return client.patch(f"/tasks/{task_id}/status", headers=headers(user), json={"status": status})


def test_full_lifecycle_visibility_and_notification(client, caplog):
    task_id = create(client)
    assert client.get("/tasks", headers=headers()).json()[0]["status"] == "CREATED"
    assert client.get("/tasks", headers=headers("2")).json() == []
    response = assign(client, task_id)
    assert response.status_code == 200
    assert response.json()["status"] == "ASSIGNED"
    assert response.json()["assigned_to"] == "2"
    assert len(client.get("/tasks", headers=headers("2")).json()) == 1
    assert client.get("/tasks", headers=headers("3")).json() == []
    notes = client.get("/notifications", headers=headers("2")).json()
    assert len(notes) == 1
    assert notes[0]["task_id"] == task_id
    assert notes[0]["user_id"] == "2"
    assert notes[0]["created_at"].endswith("Z")
    assert notes[0]["message"] in caplog.text
    assert client.get("/notifications", headers=headers("3")).json() == []
    for status in ("IN_PROGRESS", "COMPLETED"):
        response = change(client, task_id, status)
        assert response.status_code == 200
        assert response.json()["status"] == status


@pytest.mark.parametrize("user", ["2", "3"])
def test_worker_cannot_create_or_assign(client, user):
    assert client.post("/tasks", headers=headers(user), json={"title": "No"}).status_code == 403
    task_id = create(client)
    assert client.post(f"/tasks/{task_id}/assign", headers=headers(user), json={"user_id": "2"}).status_code == 403


@pytest.mark.parametrize("user", ["1", "3"])
def test_only_assigned_worker_can_update(client, user):
    task_id = create(client)
    assign(client, task_id)
    assert change(client, task_id, "IN_PROGRESS", user).status_code == 403
    assert client.get("/tasks", headers=headers()).json()[0]["status"] == "ASSIGNED"


def test_unassigned_worker_cannot_start(client):
    assert change(client, create(client), "IN_PROGRESS").status_code == 403


@pytest.mark.parametrize("current,target", [
    ("ASSIGNED", "CREATED"), ("ASSIGNED", "ASSIGNED"), ("ASSIGNED", "COMPLETED"),
    ("IN_PROGRESS", "CREATED"), ("IN_PROGRESS", "ASSIGNED"), ("IN_PROGRESS", "IN_PROGRESS"),
    ("COMPLETED", "CREATED"), ("COMPLETED", "ASSIGNED"),
    ("COMPLETED", "IN_PROGRESS"), ("COMPLETED", "COMPLETED"),
])
def test_invalid_transitions_leave_state_unchanged(client, current, target):
    task_id = create(client)
    assign(client, task_id)
    if current in ("IN_PROGRESS", "COMPLETED"):
        assert change(client, task_id, "IN_PROGRESS").status_code == 200
    if current == "COMPLETED":
        assert change(client, task_id, "COMPLETED").status_code == 200
    response = change(client, task_id, target)
    assert response.status_code == 400
    assert "Invalid transition" in response.json()["detail"]
    assert client.get("/tasks", headers=headers()).json()[0]["status"] == current


@pytest.mark.parametrize("current", ["ASSIGNED", "IN_PROGRESS", "COMPLETED"])
def test_reassignment_rejected_without_duplicate_notification(client, current):
    task_id = create(client)
    assign(client, task_id)
    if current in ("IN_PROGRESS", "COMPLETED"):
        change(client, task_id, "IN_PROGRESS")
    if current == "COMPLETED":
        change(client, task_id, "COMPLETED")
    assert assign(client, task_id, "3").status_code == 400
    assert assign(client, task_id, "2").status_code == 400
    assert len(client.get("/notifications", headers=headers("2")).json()) == 1
    assert client.get("/notifications", headers=headers("3")).json() == []


@pytest.mark.parametrize("body", [{}, {"description": "No title"}, {"title": " "}, {"title": None}, {"title": "Ok", "status": "COMPLETED"}])
def test_create_validation(client, body):
    assert client.post("/tasks", headers=headers(), json=body).status_code == 400
    assert client.get("/tasks", headers=headers()).json() == []


def test_header_and_write_validation(client):
    assert client.get("/tasks").status_code == 400
    assert client.get("/tasks", headers=headers("unknown")).status_code == 403
    task_id = create(client)
    assert client.post(f"/tasks/{task_id}/assign", headers=headers(), json={}).status_code == 400
    assert assign(client, task_id, "unknown").status_code == 404
    assert assign(client, task_id, "1").status_code == 400
    assert client.patch(f"/tasks/{task_id}/status", headers=headers("2"), json={}).status_code == 400
    assert change(client, task_id, "INVALID").status_code == 400
    assert client.post("/tasks", headers=headers(), content="{",).status_code == 400
    assert client.get("/notifications", headers=headers()).status_code == 403


def test_not_found(client):
    assert assign(client, 999).status_code == 404
    assert change(client, 999, "IN_PROGRESS").status_code == 404


def test_persistence_after_restart(tmp_path):
    path = tmp_path / "persistent.db"
    with TestClient(create_app(path)) as first:
        task_id = create(first)
        assign(first, task_id)
    with TestClient(create_app(path)) as second:
        assert second.get("/tasks", headers=headers("2")).json()[0]["id"] == task_id
        assert len(second.get("/notifications", headers=headers("2")).json()) == 1
        assert create(second) > task_id


def test_assignment_rollback_if_notification_fails(client):
    task_id = create(client)
    with sqlite3.connect(client.app.state.database_path) as db:
        db.execute("CREATE TRIGGER reject_notification BEFORE INSERT ON notifications BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        assign(client, task_id)
    task = client.get("/tasks", headers=headers()).json()[0]
    assert task["status"] == "CREATED"
    assert task["assigned_to"] is None


def test_competing_assignments_create_one_notification(client):
    task_id = create(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda worker: assign(client, task_id, worker), ["2", "3"]))
    assert sorted(r.status_code for r in responses) == [200, 400]
    notes = sum(len(client.get("/notifications", headers=headers(user)).json()) for user in ("2", "3"))
    assert notes == 1


def test_swagger_and_openapi(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "SwaggerUIBundle" in client.get("/docs").text
    schema = client.get("/openapi.json").json()
    for path, method in [("/tasks", "get"), ("/tasks", "post"), ("/tasks/{task_id}/assign", "post"), ("/tasks/{task_id}/status", "patch")]:
        operation = schema["paths"][path][method]
        assert any(p["name"] == "X-User-Id" and p["required"] for p in operation["parameters"])
        assert "400" in operation["responses"]
        assert "422" not in operation["responses"]


def test_sql_like_input_is_stored_as_data(client):
    payload = "Robert'); DROP TABLE tasks; --"
    response = client.post(
        "/tasks", headers=headers(),
        json={"title": payload, "description": "' OR 1=1 --"},
    )
    assert response.status_code == 201
    task = response.json()
    assert task["title"] == payload
    assert task["description"] == "' OR 1=1 --"
    assert create(client) > task["id"]
    assert len(client.get("/tasks", headers=headers()).json()) == 2
    assert client.get("/tasks", headers=headers("2' OR '1'='1")).status_code == 403
    assert assign(client, task["id"], "2' OR '1'='1").status_code == 404
    assert client.get("/tasks", headers=headers("2")).json() == []
