"""SQLite persistence for saved projects — a dataset + RaceConfig pair a
user can reopen later, per the optional schema in the plan doc. Plain
sqlite3 (no ORM) is enough for this scale; a connection is opened per
call rather than pooled, which is fine for a single-process dev server."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.settings import STORAGE_DIR

DB_PATH = STORAGE_DIR / "bar_race_studio.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def save_project(name: str, dataset_id: str, config_json: dict, project_id: str | None = None) -> str:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        if project_id and conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
            conn.execute(
                "UPDATE projects SET name = ?, dataset_id = ?, config_json = ?, updated_at = ? WHERE id = ?",
                (name, dataset_id, json.dumps(config_json), now, project_id),
            )
            return project_id
        new_id = project_id or uuid.uuid4().hex[:12]
        conn.execute(
            "INSERT INTO projects (id, name, dataset_id, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (new_id, name, dataset_id, json.dumps(config_json), now, now),
        )
        return new_id


def list_projects() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, dataset_id, created_at, updated_at FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_project(project_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["config"] = json.loads(result.pop("config_json"))
        return result


def delete_project(project_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cur.rowcount > 0
