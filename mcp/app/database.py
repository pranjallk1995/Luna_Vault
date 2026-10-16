"""PostgreSQL schema management and metadata repository operations."""

from typing import Any
from urllib.parse import quote

import psycopg

from .config import AppConfig

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS image_metadata (
    name text PRIMARY KEY,
    image_id uuid NOT NULL DEFAULT gen_random_uuid(),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    content_sha256 char(64) NOT NULL,
    caption text NOT NULL,
    tags text[] NOT NULL DEFAULT '{}',
    analysis_model text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    search_vector tsvector NOT NULL,
    hidden boolean NOT NULL DEFAULT false,
    favorite boolean NOT NULL DEFAULT false,
    public_url text
);
ALTER TABLE image_metadata
    ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false;
ALTER TABLE image_metadata
    ADD COLUMN IF NOT EXISTS favorite boolean NOT NULL DEFAULT false;
ALTER TABLE image_metadata
    ADD COLUMN IF NOT EXISTS public_url text;
ALTER TABLE image_metadata
    ADD COLUMN IF NOT EXISTS image_id uuid NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS image_metadata_image_id_idx
    ON image_metadata (image_id);
UPDATE image_metadata
SET search_vector =
    setweight(to_tsvector('english', regexp_replace(name, '[._-]+', ' ', 'g')), 'A') ||
    setweight(to_tsvector('english', caption), 'A') ||
    setweight(to_tsvector('english', array_to_string(tags, ' ')), 'B');
CREATE INDEX IF NOT EXISTS image_metadata_search_idx
    ON image_metadata USING gin (search_vector);
CREATE INDEX IF NOT EXISTS image_metadata_tags_idx
    ON image_metadata USING gin (tags);
CREATE INDEX IF NOT EXISTS image_metadata_sha_idx
    ON image_metadata (content_sha256);
CREATE INDEX IF NOT EXISTS image_metadata_hidden_idx
    ON image_metadata (hidden, updated_at DESC);
CREATE INDEX IF NOT EXISTS image_metadata_favorite_idx
    ON image_metadata (favorite, hidden, updated_at DESC);
CREATE TABLE IF NOT EXISTS vault_security (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    password_salt bytea NOT NULL,
    password_hash bytea NOT NULL,
    reset_pin_salt bytea NOT NULL,
    reset_pin_hash bytea NOT NULL,
    iterations integer NOT NULL CHECK (iterations >= 100000),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS vault_config (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    public_base_url text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


class MetadataRepository:
    """Persist image metadata, hidden state, credentials, and search indexes."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize this component and its required dependencies."""
        self.database_url = config.database_url

    @staticmethod
    def _row_to_metadata(row: tuple[Any, ...]) -> dict[str, Any]:
        """Convert a database row into the public metadata representation."""
        return {
            "name": row[0], "size_bytes": row[1], "content_sha256": row[2],
            "caption": row[3], "tags": row[4], "analysis_model": row[5],
            "updated_at": row[6].isoformat(), "hidden": row[7], "favorite": row[8],
            "public_url": row[9], "image_id": str(row[10]),
        }

    def initialize(self) -> None:
        """Create or upgrade the idempotent Luna Visia database schema."""
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(SCHEMA_SQL)

    def upsert(self, name: str, size_bytes: int, content_sha256: str,
               caption: str, tags: list[str], analysis_model: str,
               public_url: str | None = None) -> dict[str, Any]:
        """Insert or replace metadata and rebuild its weighted search vector."""
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                INSERT INTO image_metadata
                    (name, size_bytes, content_sha256, caption, tags, analysis_model,
                     public_url, search_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s,
                    setweight(to_tsvector('english', regexp_replace(%s, '[._-]+', ' ', 'g')), 'A') ||
                    setweight(to_tsvector('english', %s), 'A') ||
                    setweight(to_tsvector('english', %s), 'B'))
                ON CONFLICT (name) DO UPDATE SET
                    size_bytes = EXCLUDED.size_bytes,
                    content_sha256 = EXCLUDED.content_sha256,
                    caption = EXCLUDED.caption,
                    tags = EXCLUDED.tags,
                    analysis_model = EXCLUDED.analysis_model,
                    public_url = EXCLUDED.public_url,
                    search_vector = EXCLUDED.search_vector,
                    updated_at = now()
                RETURNING name, size_bytes, content_sha256, caption, tags,
                          analysis_model, updated_at, hidden, favorite, public_url,
                          image_id
                """,
                (name, size_bytes, content_sha256, caption, tags, analysis_model,
                 public_url,
                 name, caption, " ".join(tags)),
            ).fetchone()
            metadata = self._row_to_metadata(row)
            if public_url:
                public_base_url = public_url.split("/api/public/images/", 1)[0]
                stable_url = self._public_url(
                    public_base_url, metadata["image_id"]
                )
                row = connection.execute(
                    """UPDATE image_metadata SET public_url = %s WHERE name = %s
                       RETURNING name, size_bytes, content_sha256, caption, tags,
                                 analysis_model, updated_at, hidden, favorite,
                                 public_url, image_id""",
                    (stable_url, name),
                ).fetchone()
        return self._row_to_metadata(row)

    def delete(self, name: str) -> None:
        """Delete one metadata record by filename."""
        with psycopg.connect(self.database_url) as connection:
            connection.execute("DELETE FROM image_metadata WHERE name = %s", (name,))

    def rename(
        self, name: str, new_name: str, public_url: str | None = None
    ) -> dict[str, Any]:
        """Rename one visible metadata record while preserving all other fields."""
        try:
            with psycopg.connect(self.database_url) as connection:
                row = connection.execute(
                    """UPDATE image_metadata
                       SET name = %s,
                           search_vector =
                               setweight(to_tsvector('english', regexp_replace(%s, '[._-]+', ' ', 'g')), 'A') ||
                               setweight(to_tsvector('english', caption), 'A') ||
                               setweight(to_tsvector('english', array_to_string(tags, ' ')), 'B'),
                           updated_at = now()
                       WHERE name = %s AND hidden = false
                       RETURNING name, size_bytes, content_sha256, caption, tags,
                                 analysis_model, updated_at, hidden, favorite,
                                 public_url, image_id""",
                    (new_name, new_name, name),
                ).fetchone()
        except psycopg.errors.UniqueViolation as error:
            raise FileExistsError(f"Image {new_name!r} already exists.") from error
        if row is None:
            raise FileNotFoundError(f"Visible image {name!r} was not found.")
        return self._row_to_metadata(row)

    def update_metadata(
        self,
        name: str,
        caption: str,
        tags: list[str],
        hidden: bool = False,
    ) -> dict[str, Any]:
        """Update editable metadata and rebuild its full-text search vector."""
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """UPDATE image_metadata
                   SET caption = %s,
                       tags = %s,
                       search_vector =
                           setweight(to_tsvector('english', regexp_replace(name, '[._-]+', ' ', 'g')), 'A') ||
                           setweight(to_tsvector('english', %s), 'A') ||
                           setweight(to_tsvector('english', %s), 'B'),
                       updated_at = now()
                   WHERE name = %s AND hidden = %s
                   RETURNING name, size_bytes, content_sha256, caption, tags,
                             analysis_model, updated_at, hidden, favorite,
                             public_url, image_id""",
                (caption, tags, caption, " ".join(tags), name, hidden),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Image {name!r} was not found.")
        return self._row_to_metadata(row)

    def list_all(self, hidden: bool | None = False) -> list[dict[str, Any]]:
        """List visible, hidden, or all records according to ``hidden``."""
        where = "" if hidden is None else "WHERE hidden = %s"
        parameters = () if hidden is None else (hidden,)
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                f"""SELECT name, size_bytes, content_sha256, caption, tags,
                           analysis_model, updated_at, hidden, favorite, public_url,
                           image_id
                    FROM image_metadata {where}
                    ORDER BY updated_at DESC, name""",
                parameters,
            ).fetchall()
        return [self._row_to_metadata(row) for row in rows]

    def is_hidden(self, name: str) -> bool:
        """Return whether the named image belongs to the Hidden Vault."""
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                "SELECT hidden FROM image_metadata WHERE name = %s", (name,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Image {name!r} was not found.")
        return bool(row[0])

    def set_hidden(self, names: list[str], hidden: bool) -> list[str]:
        """Persist hidden state for the supplied image names."""
        if not names:
            return []
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                """UPDATE image_metadata SET hidden = %s, updated_at = now()
                   WHERE name = ANY(%s) AND hidden <> %s RETURNING name""",
                (hidden, names, hidden),
            ).fetchall()
        return [row[0] for row in rows]

    def list_favorites(self) -> list[dict[str, Any]]:
        """List visible favorite images newest first."""
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                """SELECT name, size_bytes, content_sha256, caption, tags,
                          analysis_model, updated_at, hidden, favorite, public_url,
                          image_id
                   FROM image_metadata
                   WHERE favorite = true AND hidden = false
                   ORDER BY updated_at DESC, name"""
            ).fetchall()
        return [self._row_to_metadata(row) for row in rows]

    @staticmethod
    def _public_url(public_base_url: str, image_id: str) -> str:
        return f"{public_base_url}/api/public/images/{quote(str(image_id), safe='')}"

    def name_for_image_id(self, image_id: str) -> str | None:
        """Resolve an immutable public identifier to its current filename."""
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                "SELECT name FROM image_metadata WHERE image_id::text = %s",
                (image_id,),
            ).fetchone()
        return row[0] if row else None

    def initialize_public_base_url(self, default_url: str) -> str:
        """Seed mutable URL configuration once and refresh stored image URLs."""
        with psycopg.connect(self.database_url) as connection:
            if default_url:
                connection.execute(
                    """INSERT INTO vault_config (singleton, public_base_url)
                       VALUES (true, %s)
                       ON CONFLICT (singleton) DO NOTHING""",
                    (default_url,),
                )
            row = connection.execute(
                "SELECT public_base_url FROM vault_config WHERE singleton = true"
            ).fetchone()
            public_base_url = row[0] if row else ""
            if not public_base_url:
                return ""
            images = connection.execute(
                "SELECT name, image_id FROM image_metadata"
            ).fetchall()
            with connection.cursor() as cursor:
                cursor.executemany(
                    "UPDATE image_metadata SET public_url = %s WHERE name = %s",
                    [
                        (self._public_url(public_base_url, image_id), name)
                        for name, image_id in images
                    ],
                )
        return public_base_url

    def public_base_url(self) -> str:
        """Return the currently persisted public HTTPS origin."""
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                "SELECT public_base_url FROM vault_config WHERE singleton = true"
            ).fetchone()
        return row[0] if row else ""

    def set_public_base_url(self, public_base_url: str) -> int:
        """Atomically store the origin and regenerate every image URL."""
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """INSERT INTO vault_config (singleton, public_base_url)
                   VALUES (true, %s)
                   ON CONFLICT (singleton) DO UPDATE SET
                       public_base_url = EXCLUDED.public_base_url,
                       updated_at = now()""",
                (public_base_url,),
            )
            images = connection.execute(
                "SELECT name, image_id FROM image_metadata"
            ).fetchall()
            with connection.cursor() as cursor:
                cursor.executemany(
                    "UPDATE image_metadata SET public_url = %s WHERE name = %s",
                    [
                        (self._public_url(public_base_url, image_id), name)
                        for name, image_id in images
                    ],
                )
        return len(images)

    def set_favorite(self, names: list[str], favorite: bool) -> list[str]:
        """Set favorite state for visible images."""
        if not names:
            return []
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                """UPDATE image_metadata SET favorite = %s, updated_at = now()
                   WHERE name = ANY(%s) AND hidden = false AND favorite <> %s
                   RETURNING name""",
                (favorite, names, favorite),
            ).fetchall()
        return [row[0] for row in rows]

    def security_credentials(self) -> tuple[bytes, bytes, bytes, bytes, int] | None:
        """Return the stored Hidden Vault credential material, when configured."""
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
        """Persist Hidden Vault credentials only when none exist."""
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
        """Replace the stored password-derived credential material."""
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
