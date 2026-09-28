"""SQLite storage. Each request uses its own connection and transaction."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


DEFAULT_DATABASE = Path(__file__).resolve().parent.parent / "tasks.db"


@contextmanager
def connection(database_path, *, write=False):
    db = sqlite3.connect(str(database_path), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        if write:
            # Serialize read-check-write operations, including competing assignments.
            db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(database_path):
    with connection(database_path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL CHECK(status IN
                    ('CREATED', 'ASSIGNED', 'IN_PROGRESS', 'COMPLETED')),
                assigned_to TEXT,
                CHECK ((status = 'CREATED' AND assigned_to IS NULL)
                    OR (status != 'CREATED' AND assigned_to IS NOT NULL))
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
