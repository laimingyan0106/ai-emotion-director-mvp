import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS projects (
      id UUID PRIMARY KEY,
      name VARCHAR(120) NOT NULL,
      target_duration INTEGER NOT NULL DEFAULT 30,
      status VARCHAR(32) NOT NULL DEFAULT 'draft',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audio_assets (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      filename TEXT NOT NULL,
      storage_path TEXT NOT NULL,
      content_type TEXT,
      size_bytes BIGINT NOT NULL,
      analysis JSONB,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS generated_assets (
      id BIGSERIAL PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      kind VARCHAR(40) NOT NULL,
      payload JSONB NOT NULL,
      version INTEGER NOT NULL DEFAULT 1,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS render_jobs (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      adapter VARCHAR(80) NOT NULL,
      status VARCHAR(32) NOT NULL,
      payload JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
]


class Database:
    def __init__(self, database_url: str | None = None) -> None:
        self.pool = ConnectionPool(
            conninfo=database_url or get_settings().database_url,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row},
            open=False,
        )

    def open(self) -> None:
        self.pool.open(wait=True)
        with self.connection() as connection:
            with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)
            connection.commit()

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator[Any]:
        with self.pool.connection() as connection:
            yield connection

    def insert_asset(self, project_id: UUID, kind: str, payload: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO generated_assets(project_id, kind, payload) VALUES (%s, %s, %s::jsonb)",
                (project_id, kind, json.dumps(payload, ensure_ascii=False)),
            )
            connection.execute(
                "UPDATE projects SET status = %s, updated_at = NOW() WHERE id = %s",
                (kind, project_id),
            )
            connection.commit()


class SqliteDatabase:
    """Small zero-config store for T002 hosted integration.

    Vercel's /tmp filesystem is ephemeral. Durable, cross-device persistence is
    intentionally deferred to T003.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  target_duration INTEGER NOT NULL DEFAULT 30,
                  status TEXT NOT NULL DEFAULT 'draft',
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS audio_assets (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                  filename TEXT NOT NULL,
                  storage_path TEXT NOT NULL,
                  content_type TEXT,
                  size_bytes INTEGER NOT NULL,
                  analysis TEXT,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS generated_assets (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                  kind TEXT NOT NULL,
                  payload TEXT NOT NULL,
                  version INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS render_jobs (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                  adapter TEXT NOT NULL,
                  status TEXT NOT NULL,
                  payload TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def close(self) -> None:
        return None

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def insert_asset(self, project_id: UUID, kind: str, payload: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO generated_assets(project_id, kind, payload) VALUES (?, ?, ?)",
                (str(project_id), kind, json.dumps(payload, ensure_ascii=False)),
            )
            connection.execute(
                "UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (kind, str(project_id)),
            )
            connection.commit()


settings = get_settings()
database: Database | SqliteDatabase
if settings.resolved_storage_mode == "sqlite":
    database = SqliteDatabase(settings.resolved_sqlite_path)
else:
    database = Database()


def create_project_record(project_id: UUID, name: str, target_duration: int) -> None:
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            connection.execute(
                "INSERT INTO projects(id, name, target_duration) VALUES (?, ?, ?)",
                (str(project_id), name, target_duration),
            )
        else:
            connection.execute(
                "INSERT INTO projects(id, name, target_duration) VALUES (%s, %s, %s)",
                (project_id, name, target_duration),
            )
        connection.commit()


def list_project_records() -> list[dict[str, Any]]:
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            rows = connection.execute(
                """
                SELECT * FROM projects
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM projects
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()
    return [_normalize_project(dict(row)) for row in rows]


def update_project_record(
    project_id: UUID,
    *,
    name: str | None = None,
    target_duration: int | None = None,
) -> dict[str, Any] | None:
    updates: list[tuple[str, Any]] = []
    if name is not None:
        updates.append(("name", name))
    if target_duration is not None:
        updates.append(("target_duration", target_duration))
    if not updates:
        return get_project_record(project_id)

    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            assignments = ", ".join(f"{column} = ?" for column, _ in updates)
            values = [value for _, value in updates]
            cursor = connection.execute(
                f"""
                UPDATE projects SET {assignments}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (*values, str(project_id)),
            )
        else:
            assignments = ", ".join(f"{column} = %s" for column, _ in updates)
            values = [value for _, value in updates]
            cursor = connection.execute(
                f"""
                UPDATE projects SET {assignments}, updated_at = NOW()
                WHERE id = %s
                """,
                (*values, project_id),
            )
        connection.commit()
        if cursor.rowcount == 0:
            return None
    return get_project_record(project_id)


def delete_project_record(project_id: UUID) -> list[str] | None:
    with database.connection() as connection:
        project_query = "SELECT id FROM projects WHERE id = ?" if isinstance(database, SqliteDatabase) else "SELECT id FROM projects WHERE id = %s"
        project = connection.execute(project_query, (str(project_id),) if isinstance(database, SqliteDatabase) else (project_id,)).fetchone()
        if not project:
            return None

        audio_query = (
            "SELECT storage_path FROM audio_assets WHERE project_id = ?"
            if isinstance(database, SqliteDatabase)
            else "SELECT storage_path FROM audio_assets WHERE project_id = %s"
        )
        audio_rows = connection.execute(
            audio_query,
            (str(project_id),) if isinstance(database, SqliteDatabase) else (project_id,),
        ).fetchall()
        storage_paths = [str(row["storage_path"]) for row in audio_rows]

        if isinstance(database, SqliteDatabase):
            for table in ("render_jobs", "generated_assets", "audio_assets"):
                connection.execute(f"DELETE FROM {table} WHERE project_id = ?", (str(project_id),))
            connection.execute("DELETE FROM projects WHERE id = ?", (str(project_id),))
        else:
            connection.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        connection.commit()
    return storage_paths


def count_project_dependents(project_id: UUID) -> dict[str, int]:
    result: dict[str, int] = {}
    with database.connection() as connection:
        for table in ("audio_assets", "generated_assets", "render_jobs"):
            if isinstance(database, SqliteDatabase):
                row = connection.execute(
                    f"SELECT COUNT(*) AS count FROM {table} WHERE project_id = ?",
                    (str(project_id),),
                ).fetchone()
            else:
                row = connection.execute(
                    f"SELECT COUNT(*) AS count FROM {table} WHERE project_id = %s",
                    (project_id,),
                ).fetchone()
            result[table] = int(row["count"])
    return result


def _normalize_project(result: dict[str, Any]) -> dict[str, Any]:
    result["id"] = UUID(str(result["id"]))
    return result


def save_audio_record(
    audio_id: UUID,
    project_id: UUID,
    filename: str,
    storage_path: str,
    content_type: str | None,
    size: int,
) -> None:
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            connection.execute(
                """
                INSERT INTO audio_assets(id, project_id, filename, storage_path, content_type, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(audio_id), str(project_id), filename, storage_path, content_type, size),
            )
        else:
            connection.execute(
                """
                INSERT INTO audio_assets(id, project_id, filename, storage_path, content_type, size_bytes)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (audio_id, project_id, filename, storage_path, content_type, size),
            )
        connection.commit()


def get_project_record(project_id: UUID) -> dict[str, Any] | None:
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            project = connection.execute("SELECT * FROM projects WHERE id = ?", (str(project_id),)).fetchone()
            audio = connection.execute(
                """
                SELECT id, filename, content_type, size_bytes, created_at
                FROM audio_assets WHERE project_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                (str(project_id),),
            ).fetchone()
        else:
            project = connection.execute("SELECT * FROM projects WHERE id = %s", (project_id,)).fetchone()
            audio = connection.execute(
                """
                SELECT id, filename, content_type, size_bytes, created_at
                FROM audio_assets WHERE project_id = %s ORDER BY created_at DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
    if not project:
        return None
    result = _normalize_project(dict(project))
    if audio:
        audio_result = dict(audio)
        audio_result["id"] = UUID(str(audio_result["id"]))
        result["audio"] = audio_result
    else:
        result["audio"] = None
    return result


def get_latest_audio(project_id: UUID) -> dict[str, Any] | None:
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            row = connection.execute(
                "SELECT id, storage_path FROM audio_assets WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (str(project_id),),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT id, storage_path FROM audio_assets WHERE project_id = %s ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
    return dict(row) if row else None


def save_audio_analysis(audio_id: UUID | str, analysis: dict[str, Any]) -> None:
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            connection.execute(
                "UPDATE audio_assets SET analysis = ? WHERE id = ?",
                (json.dumps(analysis, ensure_ascii=False), str(audio_id)),
            )
        else:
            connection.execute(
                "UPDATE audio_assets SET analysis = %s::jsonb WHERE id = %s",
                (json.dumps(analysis, ensure_ascii=False), audio_id),
            )
        connection.commit()


def load_project_context(project_id: UUID) -> dict[str, Any] | None:
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            project = connection.execute("SELECT * FROM projects WHERE id = ?", (str(project_id),)).fetchone()
            assets = connection.execute(
                "SELECT kind, payload FROM generated_assets WHERE project_id = ? ORDER BY created_at",
                (str(project_id),),
            ).fetchall()
        else:
            project = connection.execute("SELECT * FROM projects WHERE id = %s", (project_id,)).fetchone()
            assets = connection.execute(
                "SELECT kind, payload FROM generated_assets WHERE project_id = %s ORDER BY created_at",
                (project_id,),
            ).fetchall()
    if not project:
        return None
    parsed_assets: dict[str, Any] = {}
    for row in assets:
        value = row["payload"]
        parsed_assets[row["kind"]] = json.loads(value) if isinstance(value, str) else value
    return {"project": dict(project), "assets": parsed_assets}


def create_render_job(project_id: UUID, adapter: str, job: dict[str, Any]) -> UUID:
    job_id = uuid4()
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            connection.execute(
                "INSERT INTO render_jobs(id, project_id, adapter, status, payload) VALUES (?, ?, ?, ?, ?)",
                (str(job_id), str(project_id), adapter, "queued", json.dumps(job)),
            )
        else:
            connection.execute(
                "INSERT INTO render_jobs(id, project_id, adapter, status, payload) VALUES (%s, %s, %s, %s, %s::jsonb)",
                (job_id, project_id, adapter, "queued", json.dumps(job)),
            )
        connection.commit()
    return job_id
