"""PostgreSQL schema management and metadata repository operations."""

from typing import Any

import psycopg

from config import AppConfig

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS image_metadata (
    name text PRIMARY KEY,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    content_sha256 char(64) NOT NULL,
    caption text NOT NULL,
    tags text[] NOT NULL DEFAULT '{}',
    analysis_model text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    search_vector tsvector NOT NULL,
    hidden boolean NOT NULL DEFAULT false
);
ALTER TABLE image_metadata
    ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS image_metadata_search_idx
    ON image_metadata USING gin (search_vector);
CREATE INDEX IF NOT EXISTS image_metadata_tags_idx
    ON image_metadata USING gin (tags);
CREATE INDEX IF NOT EXISTS image_metadata_sha_idx
    ON image_metadata (content_sha256);
CREATE INDEX IF NOT EXISTS image_metadata_hidden_idx
    ON image_metadata (hidden, updated_at DESC);
CREATE TABLE IF NOT EXISTS vault_security (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    password_salt bytea NOT NULL,
    password_hash bytea NOT NULL,
    reset_pin_salt bytea NOT NULL,
    reset_pin_hash bytea NOT NULL,
    iterations integer NOT NULL CHECK (iterations >= 100000),
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


class MetadataRepository:
    """Persist image metadata, hidden state, credentials, and search indexes."""

    def __init__(self, config: AppConfig) -> None:
        self.database_url = config.database_url

    @staticmethod
    def _row_to_metadata(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "name": row[0], "size_bytes": row[1], "content_sha256": row[2],
            "caption": row[3], "tags": row[4], "analysis_model": row[5],
            "updated_at": row[6].isoformat(), "hidden": row[7],
        }

    def initialize(self) -> None:
        """Create or upgrade the idempotent Luna Vault database schema."""
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(SCHEMA_SQL)

    def upsert(self, name: str, size_bytes: int, content_sha256: str,
               caption: str, tags: list[str], analysis_model: str) -> dict[str, Any]:
        """Insert or replace metadata and rebuild its weighted search vector."""
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                INSERT INTO image_metadata
                    (name, size_bytes, content_sha256, caption, tags, analysis_model, search_vector)
                VALUES (%s, %s, %s, %s, %s, %s,
                    setweight(to_tsvector('english', %s), 'A') ||
                    setweight(to_tsvector('english', %s), 'B'))
                ON CONFLICT (name) DO UPDATE SET
                    size_bytes = EXCLUDED.size_bytes,
                    content_sha256 = EXCLUDED.content_sha256,
                    caption = EXCLUDED.caption,
                    tags = EXCLUDED.tags,
                    analysis_model = EXCLUDED.analysis_model,
                    search_vector = EXCLUDED.search_vector,
                    updated_at = now()
                RETURNING name, size_bytes, content_sha256, caption, tags,
                          analysis_model, updated_at, hidden
                """,
                (name, size_bytes, content_sha256, caption, tags, analysis_model,
                 caption, " ".join(tags)),
            ).fetchone()
        return self._row_to_metadata(row)

    def delete(self, name: str) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute("DELETE FROM image_metadata WHERE name = %s", (name,))

    def list_all(self, hidden: bool | None = False) -> list[dict[str, Any]]:
        """List visible, hidden, or all records according to ``hidden``."""
        where = "" if hidden is None else "WHERE hidden = %s"
        parameters = () if hidden is None else (hidden,)
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                f"""SELECT name, size_bytes, content_sha256, caption, tags,
                           analysis_model, updated_at, hidden
                    FROM image_metadata {where}
                    ORDER BY updated_at DESC, name""",
                parameters,
            ).fetchall()
        return [self._row_to_metadata(row) for row in rows]

    def is_hidden(self, name: str) -> bool:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                "SELECT hidden FROM image_metadata WHERE name = %s", (name,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Image {name!r} was not found.")
        return bool(row[0])

    def set_hidden(self, names: list[str], hidden: bool) -> list[str]:
        if not names:
            return []
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                """UPDATE image_metadata SET hidden = %s, updated_at = now()
                   WHERE name = ANY(%s) AND hidden <> %s RETURNING name""",
                (hidden, names, hidden),
            ).fetchall()
        return [row[0] for row in rows]

    def security_credentials(self) -> tuple[bytes, bytes, bytes, bytes, int] | None:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """SELECT password_salt, password_hash, reset_pin_salt,
                          reset_pin_hash, iterations
                   FROM vault_security WHERE singleton = true"""
            ).fetchone()
        return tuple(row) if row else None

    def create_security_credentials(self, password_salt: bytes, password_hash: bytes,
                                    pin_salt: bytes, pin_hash: bytes,
                                    iterations: int) -> bool:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """INSERT INTO vault_security
                       (singleton, password_salt, password_hash, reset_pin_salt,
                        reset_pin_hash, iterations)
                   VALUES (true, %s, %s, %s, %s, %s)
                   ON CONFLICT (singleton) DO NOTHING RETURNING singleton""",
                (password_salt, password_hash, pin_salt, pin_hash, iterations),
            ).fetchone()
        return row is not None

    def update_password(self, password_salt: bytes, password_hash: bytes,
                        iterations: int) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE vault_security SET password_salt = %s,
                       password_hash = %s, iterations = %s, updated_at = now()
                   WHERE singleton = true""",
                (password_salt, password_hash, iterations),
            )

    def search(self, normalized_query: str, tags: list[str], match_all_tags: bool,
               limit: int, offset: int) -> tuple[int, list[dict[str, Any]]]:
        """Query persisted full-text and tag indexes without opening images."""
        tag_operator = "@>" if match_all_tags else "&&"
        clauses = ["hidden = false"]
        parameters: list[Any] = []
        if normalized_query:
            clauses.append("search_vector @@ websearch_to_tsquery('english', %s)")
            parameters.append(normalized_query)
        if tags:
            clauses.append(f"tags {tag_operator} %s")
            parameters.append(tags)
        rank_sql = (
            "ts_rank_cd(search_vector, websearch_to_tsquery('english', %s))"
            if normalized_query else "0"
        )
        query_parameters = ([normalized_query] if normalized_query else []) + parameters + [limit, offset]
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                f"""SELECT name, caption, tags, updated_at,
                           count(*) OVER() AS total_count, {rank_sql} AS rank
                    FROM image_metadata WHERE {' AND '.join(clauses)}
                    ORDER BY rank DESC, updated_at DESC, name LIMIT %s OFFSET %s""",
                query_parameters,
            ).fetchall()
        count = rows[0][4] if rows else 0
        results = [{"name": row[0], "caption": row[1], "tags": row[2],
                    "updated_at": row[3].isoformat()} for row in rows]
        return count, results
