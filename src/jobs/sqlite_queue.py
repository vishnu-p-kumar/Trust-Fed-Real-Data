"""Small durable SQLite job queue for local/single-host deployments.

For multiple workers or horizontally scaled production deployments, replace this with
PostgreSQL-backed queueing or a broker such as Redis/RabbitMQ and a dedicated worker.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SQLiteJobQueue:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, result TEXT, error TEXT)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at)")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def enqueue(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not kind.strip():
            raise ValueError("job kind is required")
        job_id, now = uuid.uuid4().hex, self._now()
        with self._connect() as db:
            db.execute("INSERT INTO jobs(id,kind,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                       (job_id, kind, json.dumps(payload, allow_nan=False), "queued", now, now))
        return self.get(job_id)  # type: ignore[return-value]

    def claim(self) -> dict[str, Any] | None:
        now = self._now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                db.commit()
                return None
            changed = db.execute("UPDATE jobs SET status='running', attempts=attempts+1, updated_at=? WHERE id=? AND status='queued'",
                                  (now, row["id"])).rowcount
            db.commit()
            return self.get(row["id"]) if changed else None

    def finish(self, job_id: str, result: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            changed = db.execute("UPDATE jobs SET status='completed', result=?, error=NULL, updated_at=? WHERE id=? AND status='running'",
                                 (json.dumps(result, allow_nan=False), self._now(), job_id)).rowcount
            if not changed:
                raise ValueError("job does not exist or is not running")
        return self.get(job_id)  # type: ignore[return-value]

    def fail(self, job_id: str, error: str) -> dict[str, Any]:
        with self._connect() as db:
            changed = db.execute("UPDATE jobs SET status='failed', error=?, updated_at=? WHERE id=? AND status='running'",
                                 (str(error)[:2000], self._now(), job_id)).rowcount
            if not changed:
                raise ValueError("job does not exist or is not running")
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key in ("payload", "result"):
            if result.get(key):
                result[key] = json.loads(result[key])
        return result
