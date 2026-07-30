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
      status VARCHAR(24) NOT NULL DEFAULT 'draft',
      is_active BOOLEAN NOT NULL DEFAULT FALSE,
      parent_asset_id BIGINT REFERENCES generated_assets(id) ON DELETE SET NULL,
      provider VARCHAR(80),
      model VARCHAR(120),
      prompt TEXT,
      input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
      validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
                cursor.execute(
                    """
                    ALTER TABLE generated_assets
                      ADD COLUMN IF NOT EXISTS status VARCHAR(24) NOT NULL DEFAULT 'draft',
                      ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE,
                      ADD COLUMN IF NOT EXISTS parent_asset_id BIGINT REFERENCES generated_assets(id) ON DELETE SET NULL,
                      ADD COLUMN IF NOT EXISTS provider VARCHAR(80),
                      ADD COLUMN IF NOT EXISTS model VARCHAR(120),
                      ADD COLUMN IF NOT EXISTS prompt TEXT,
                      ADD COLUMN IF NOT EXISTS input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
                      ADD COLUMN IF NOT EXISTS validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
                      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    """
                )
                cursor.execute(
                    """
                    WITH ranked AS (
                      SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY project_id, kind ORDER BY created_at, id
                      ) AS next_version
                      FROM generated_assets
                    )
                    UPDATE generated_assets AS asset
                    SET version = ranked.next_version
                    FROM ranked
                    WHERE asset.id = ranked.id
                    """
                )
                cursor.execute(
                    """
                    UPDATE generated_assets
                    SET status = 'archived'
                    WHERE status = 'draft' AND NOT is_active
                    """
                )
                cursor.execute(
                    """
                    UPDATE generated_assets AS asset
                    SET status = 'active', is_active = TRUE
                    WHERE asset.status = 'archived'
                      AND NOT EXISTS (
                        SELECT 1
                        FROM generated_assets AS current_active
                        WHERE current_active.project_id = asset.project_id
                          AND current_active.kind = asset.kind
                          AND current_active.is_active
                      )
                      AND asset.id = (
                      SELECT latest.id
                      FROM generated_assets AS latest
                      WHERE latest.project_id = asset.project_id
                        AND latest.kind = asset.kind
                        AND latest.status = 'archived'
                      ORDER BY latest.version DESC, latest.id DESC
                      LIMIT 1
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS generated_assets_project_kind_version_uidx
                    ON generated_assets(project_id, kind, version)
                    """
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS generated_assets_one_active_uidx
                    ON generated_assets(project_id, kind)
                    WHERE is_active
                    """
                )
            connection.commit()

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator[Any]:
        with self.pool.connection() as connection:
            yield connection

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
                  status TEXT NOT NULL DEFAULT 'draft',
                  is_active INTEGER NOT NULL DEFAULT 0,
                  parent_asset_id INTEGER REFERENCES generated_assets(id) ON DELETE SET NULL,
                  provider TEXT,
                  model TEXT,
                  prompt TEXT,
                  input_snapshot TEXT NOT NULL DEFAULT '{}',
                  validation_errors TEXT NOT NULL DEFAULT '[]',
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(generated_assets)").fetchall()
            }
            migrations = {
                "status": "ALTER TABLE generated_assets ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'",
                "is_active": "ALTER TABLE generated_assets ADD COLUMN is_active INTEGER NOT NULL DEFAULT 0",
                "parent_asset_id": "ALTER TABLE generated_assets ADD COLUMN parent_asset_id INTEGER REFERENCES generated_assets(id) ON DELETE SET NULL",
                "provider": "ALTER TABLE generated_assets ADD COLUMN provider TEXT",
                "model": "ALTER TABLE generated_assets ADD COLUMN model TEXT",
                "prompt": "ALTER TABLE generated_assets ADD COLUMN prompt TEXT",
                "input_snapshot": "ALTER TABLE generated_assets ADD COLUMN input_snapshot TEXT NOT NULL DEFAULT '{}'",
                "validation_errors": "ALTER TABLE generated_assets ADD COLUMN validation_errors TEXT NOT NULL DEFAULT '[]'",
                "updated_at": "ALTER TABLE generated_assets ADD COLUMN updated_at TEXT",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    connection.execute(statement)
            connection.execute(
                """
                UPDATE generated_assets
                SET version = (
                  SELECT COUNT(*)
                  FROM generated_assets AS earlier
                  WHERE earlier.project_id = generated_assets.project_id
                    AND earlier.kind = generated_assets.kind
                    AND earlier.id <= generated_assets.id
                )
                """
            )
            connection.execute(
                """
                UPDATE generated_assets
                SET status = 'archived'
                WHERE status = 'draft' AND is_active = 0
                """
            )
            connection.execute(
                """
                UPDATE generated_assets
                SET status = 'active', is_active = 1
                WHERE id IN (
                  SELECT MAX(candidate.id)
                  FROM generated_assets AS candidate
                  WHERE candidate.status = 'archived'
                    AND NOT EXISTS (
                      SELECT 1
                      FROM generated_assets AS current_active
                      WHERE current_active.project_id = candidate.project_id
                        AND current_active.kind = candidate.kind
                        AND current_active.is_active = 1
                    )
                  GROUP BY candidate.project_id, candidate.kind
                )
                """
            )
            connection.execute(
                """
                UPDATE generated_assets
                SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS generated_assets_project_kind_version_uidx
                ON generated_assets(project_id, kind, version)
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS generated_assets_one_active_uidx
                ON generated_assets(project_id, kind)
                WHERE is_active = 1
                """
            )
            connection.commit()

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
        storage_paths = {str(row["storage_path"]) for row in audio_rows}
        asset_query = (
            "SELECT payload FROM generated_assets WHERE project_id = ?"
            if isinstance(database, SqliteDatabase)
            else "SELECT payload FROM generated_assets WHERE project_id = %s"
        )
        asset_rows = connection.execute(
            asset_query,
            (str(project_id),) if isinstance(database, SqliteDatabase) else (project_id,),
        ).fetchall()
        for row in asset_rows:
            payload = _decode_json(row["payload"], {})
            for reference in payload.get("reference_images", []):
                storage_path = reference.get("storage_path")
                if storage_path:
                    storage_paths.add(str(storage_path))

        if isinstance(database, SqliteDatabase):
            for table in ("render_jobs", "generated_assets", "audio_assets"):
                connection.execute(f"DELETE FROM {table} WHERE project_id = ?", (str(project_id),))
            connection.execute("DELETE FROM projects WHERE id = ?", (str(project_id),))
        else:
            connection.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        connection.commit()
    return sorted(storage_paths)


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
                """
                SELECT id, storage_path, filename, analysis
                FROM audio_assets
                WHERE project_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                (str(project_id),),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT id, storage_path, filename, analysis
                FROM audio_assets
                WHERE project_id = %s ORDER BY created_at DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["analysis"] = _decode_json(result.get("analysis"), None)
    return result


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


def _decode_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        return json.loads(value)
    return value


def _normalize_asset(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["project_id"] = UUID(str(result["project_id"]))
    result["payload"] = _decode_json(result.get("payload"), {})
    result["input_snapshot"] = _decode_json(result.get("input_snapshot"), {})
    result["validation_errors"] = _decode_json(result.get("validation_errors"), [])
    result["is_active"] = bool(result["is_active"])
    return result


def list_asset_versions(
    project_id: UUID,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    conditions = ["project_id = ?" if isinstance(database, SqliteDatabase) else "project_id = %s"]
    values: list[Any] = [str(project_id) if isinstance(database, SqliteDatabase) else project_id]
    if kind is not None:
        conditions.append("kind = ?" if isinstance(database, SqliteDatabase) else "kind = %s")
        values.append(kind)
    with database.connection() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM generated_assets
            WHERE {' AND '.join(conditions)}
            ORDER BY kind, version DESC, id DESC
            """,
            tuple(values),
        ).fetchall()
    return [_normalize_asset(row) for row in rows]


def get_active_asset_snapshot(
    project_id: UUID,
    *,
    exclude_kind: str | None = None,
) -> dict[str, dict[str, int]]:
    assets = list_asset_versions(project_id)
    return {
        asset["kind"]: {"asset_id": int(asset["id"]), "version": int(asset["version"])}
        for asset in assets
        if asset["is_active"] and asset["kind"] != exclude_kind
    }


def insert_asset_version(
    project_id: UUID,
    kind: str,
    payload: dict[str, Any],
    *,
    activate: bool,
    provider: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    input_snapshot: dict[str, Any] | None = None,
    validation_errors: list[Any] | None = None,
) -> dict[str, Any]:
    snapshot = input_snapshot or {}
    errors = validation_errors or []
    status = "draft" if activate else "failed"
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT id FROM generated_assets
                WHERE project_id = ? AND kind = ? AND is_active = 1
                """,
                (str(project_id), kind),
            ).fetchone()
            version_row = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS version
                FROM generated_assets WHERE project_id = ? AND kind = ?
                """,
                (str(project_id), kind),
            ).fetchone()
            cursor = connection.execute(
                """
                INSERT INTO generated_assets(
                  project_id, kind, payload, version, status, is_active,
                  parent_asset_id, provider, model, prompt, input_snapshot,
                  validation_errors
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(project_id),
                    kind,
                    json.dumps(payload, ensure_ascii=False),
                    int(version_row["version"]),
                    status,
                    current["id"] if current else None,
                    provider,
                    model,
                    prompt,
                    json.dumps(snapshot, ensure_ascii=False),
                    json.dumps(errors, ensure_ascii=False),
                ),
            )
            asset_id = int(cursor.lastrowid)
            if activate:
                connection.execute(
                    """
                    UPDATE generated_assets
                    SET status = 'archived', is_active = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE project_id = ? AND kind = ? AND is_active = 1
                    """,
                    (str(project_id), kind),
                )
                connection.execute(
                    """
                    UPDATE generated_assets
                    SET status = 'active', is_active = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (asset_id,),
                )
                connection.execute(
                    """
                    UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (kind, str(project_id)),
                )
        else:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"{project_id}:{kind}",),
            )
            current = connection.execute(
                """
                SELECT id FROM generated_assets
                WHERE project_id = %s AND kind = %s AND is_active
                FOR UPDATE
                """,
                (project_id, kind),
            ).fetchone()
            version_row = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS version
                FROM generated_assets WHERE project_id = %s AND kind = %s
                """,
                (project_id, kind),
            ).fetchone()
            inserted = connection.execute(
                """
                INSERT INTO generated_assets(
                  project_id, kind, payload, version, status, is_active,
                  parent_asset_id, provider, model, prompt, input_snapshot,
                  validation_errors
                )
                VALUES (
                  %s, %s, %s::jsonb, %s, %s, FALSE, %s, %s, %s, %s,
                  %s::jsonb, %s::jsonb
                )
                RETURNING id
                """,
                (
                    project_id,
                    kind,
                    json.dumps(payload, ensure_ascii=False),
                    int(version_row["version"]),
                    status,
                    current["id"] if current else None,
                    provider,
                    model,
                    prompt,
                    json.dumps(snapshot, ensure_ascii=False),
                    json.dumps(errors, ensure_ascii=False),
                ),
            ).fetchone()
            asset_id = int(inserted["id"])
            if activate:
                connection.execute(
                    """
                    UPDATE generated_assets
                    SET status = 'archived', is_active = FALSE, updated_at = NOW()
                    WHERE project_id = %s AND kind = %s AND is_active
                    """,
                    (project_id, kind),
                )
                connection.execute(
                    """
                    UPDATE generated_assets
                    SET status = 'active', is_active = TRUE, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (asset_id,),
                )
                connection.execute(
                    """
                    UPDATE projects SET status = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (kind, project_id),
                )
        connection.commit()
    return next(asset for asset in list_asset_versions(project_id, kind) if asset["id"] == asset_id)


def activate_asset_version(
    project_id: UUID,
    kind: str,
    *,
    asset_id: int | None = None,
    version: int | None = None,
) -> dict[str, Any] | None:
    selector = "id" if asset_id is not None else "version"
    selected_value = asset_id if asset_id is not None else version
    placeholder = "?" if isinstance(database, SqliteDatabase) else "%s"
    project_value = str(project_id) if isinstance(database, SqliteDatabase) else project_id
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            connection.execute("BEGIN IMMEDIATE")
        else:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"{project_id}:{kind}",),
            )
        target = connection.execute(
            f"""
            SELECT * FROM generated_assets
            WHERE project_id = {placeholder} AND kind = {placeholder}
              AND {selector} = {placeholder}
            """,
            (project_value, kind, selected_value),
        ).fetchone()
        if not target:
            connection.rollback()
            return None
        if target["status"] == "failed":
            connection.rollback()
            raise ValueError("Failed asset versions cannot be activated")
        if isinstance(database, SqliteDatabase):
            connection.execute(
                """
                UPDATE generated_assets
                SET status = 'archived', is_active = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND kind = ? AND is_active = 1
                """,
                (str(project_id), kind),
            )
            connection.execute(
                """
                UPDATE generated_assets
                SET status = 'active', is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (target["id"],),
            )
        else:
            connection.execute(
                """
                UPDATE generated_assets
                SET status = 'archived', is_active = FALSE, updated_at = NOW()
                WHERE project_id = %s AND kind = %s AND is_active
                """,
                (project_id, kind),
            )
            connection.execute(
                """
                UPDATE generated_assets
                SET status = 'active', is_active = TRUE, updated_at = NOW()
                WHERE id = %s
                """,
                (target["id"],),
            )
        connection.commit()
    return next(
        asset
        for asset in list_asset_versions(project_id, kind)
        if asset["id"] == int(target["id"])
    )


def get_asset_dependency_warnings(project_id: UUID) -> list[dict[str, Any]]:
    assets = list_asset_versions(project_id)
    active_by_kind = {asset["kind"]: asset for asset in assets if asset["is_active"]}
    warnings: list[dict[str, Any]] = []
    for downstream in active_by_kind.values():
        for upstream_kind, expected in downstream["input_snapshot"].items():
            current = active_by_kind.get(upstream_kind)
            if (
                current
                and isinstance(expected, dict)
                and int(expected.get("asset_id", current["id"])) != int(current["id"])
            ):
                warnings.append(
                    {
                        "asset_id": int(downstream["id"]),
                        "kind": downstream["kind"],
                        "version": int(downstream["version"]),
                        "upstream_kind": upstream_kind,
                        "expected_asset_id": int(expected["asset_id"]),
                        "active_asset_id": int(current["id"]),
                        "message": (
                            f"{downstream['kind']} v{downstream['version']} depends on "
                            f"{upstream_kind} asset {expected['asset_id']}, but "
                            f"asset {current['id']} is active"
                        ),
                    }
                )
    return warnings


def load_project_context(project_id: UUID) -> dict[str, Any] | None:
    with database.connection() as connection:
        if isinstance(database, SqliteDatabase):
            project = connection.execute("SELECT * FROM projects WHERE id = ?", (str(project_id),)).fetchone()
            assets = connection.execute(
                """
                SELECT id, kind, version, payload
                FROM generated_assets
                WHERE project_id = ? AND is_active = 1
                ORDER BY kind
                """,
                (str(project_id),),
            ).fetchall()
        else:
            project = connection.execute("SELECT * FROM projects WHERE id = %s", (project_id,)).fetchone()
            assets = connection.execute(
                """
                SELECT id, kind, version, payload
                FROM generated_assets
                WHERE project_id = %s AND is_active
                ORDER BY kind
                """,
                (project_id,),
            ).fetchall()
    if not project:
        return None
    parsed_assets: dict[str, Any] = {}
    versions: dict[str, dict[str, int]] = {}
    for row in assets:
        value = row["payload"]
        parsed_assets[row["kind"]] = json.loads(value) if isinstance(value, str) else value
        versions[row["kind"]] = {
            "asset_id": int(row["id"]),
            "version": int(row["version"]),
        }
    return {
        "project": dict(project),
        "assets": parsed_assets,
        "asset_versions": versions,
    }


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
