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
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(caption, '')), 'A') ||
        setweight(to_tsvector('english', array_to_string(tags, ' ')), 'B')
    ) STORED
);
CREATE INDEX IF NOT EXISTS image_metadata_search_idx
    ON image_metadata USING gin (search_vector);
CREATE INDEX IF NOT EXISTS image_metadata_tags_idx
    ON image_metadata USING gin (tags);
CREATE INDEX IF NOT EXISTS image_metadata_sha_idx
    ON image_metadata (content_sha256);
"""


class MetadataRepository:
    def __init__(self, config: AppConfig) -> None:
        self.database_url = config.database_url

    @staticmethod
    def _row_to_metadata(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "name": row[0],
            "size_bytes": row[1],
            "content_sha256": row[2],
            "caption": row[3],
            "tags": row[4],
            "analysis_model": row[5],
            "updated_at": row[6].isoformat(),
        }

    def initialize(self) -> None:
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(SCHEMA_SQL)

    def upsert(
        self,
        name: str,
        size_bytes: int,
        content_sha256: str,
        caption: str,
        tags: list[str],
        analysis_model: str,
    ) -> dict[str, Any]:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                INSERT INTO image_metadata
                    (name, size_bytes, content_sha256, caption, tags, analysis_model)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    size_bytes = EXCLUDED.size_bytes,
                    content_sha256 = EXCLUDED.content_sha256,
                    caption = EXCLUDED.caption,
                    tags = EXCLUDED.tags,
                    analysis_model = EXCLUDED.analysis_model,
                    updated_at = now()
                RETURNING name, size_bytes, content_sha256, caption, tags,
                          analysis_model, updated_at
                """,
                (name, size_bytes, content_sha256, caption, tags, analysis_model),
            ).fetchone()
        return self._row_to_metadata(row)

    def delete(self, name: str) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute("DELETE FROM image_metadata WHERE name = %s", (name,))

    def list_all(self) -> list[dict[str, Any]]:
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                """
                SELECT name, size_bytes, content_sha256, caption, tags,
                       analysis_model, updated_at
                FROM image_metadata
                ORDER BY updated_at DESC, name
                """
            ).fetchall()
        return [self._row_to_metadata(row) for row in rows]

    def search(
        self,
        normalized_query: str,
        tags: list[str],
        match_all_tags: bool,
        limit: int,
        offset: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        tag_operator = "@>" if match_all_tags else "&&"
        clauses = []
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
        query_parameters = (
            ([normalized_query] if normalized_query else [])
            + parameters
            + [limit, offset]
        )
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                f"""
                SELECT name, caption, tags, updated_at,
                       count(*) OVER() AS total_count, {rank_sql} AS rank
                FROM image_metadata
                WHERE {" AND ".join(clauses)}
                ORDER BY rank DESC, updated_at DESC, name
                LIMIT %s OFFSET %s
                """,
                query_parameters,
            ).fetchall()
        count = rows[0][4] if rows else 0
        results = [
            {
                "name": row[0],
                "caption": row[1],
                "tags": row[2],
                "updated_at": row[3].isoformat(),
            }
            for row in rows
        ]
        return count, results


