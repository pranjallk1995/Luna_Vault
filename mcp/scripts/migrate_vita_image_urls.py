"""Replace Luna Vita filename-based Visia URLs with immutable-ID URLs."""

import os
from urllib.parse import unquote, urlparse

import psycopg


def main() -> None:
    visia_database_url = os.environ["DATABASE_URL"]
    vita_database_url = os.environ["LUNAVITA_DATABASE_URL"]

    with psycopg.connect(visia_database_url) as visia_connection:
        mappings = dict(
            visia_connection.execute(
                "SELECT name, public_url FROM image_metadata"
            ).fetchall()
        )

    updated = 0
    with psycopg.connect(vita_database_url) as vita_connection:
        rows = vita_connection.execute(
            "SELECT id, image_url FROM food_entries WHERE image_url IS NOT NULL"
        ).fetchall()
        for entry_id, image_url in rows:
            if not image_url or image_url.startswith("data:image/"):
                continue
            filename = unquote(urlparse(image_url).path.rsplit("/", 1)[-1])
            stable_url = mappings.get(filename)
            if stable_url and stable_url != image_url:
                vita_connection.execute(
                    "UPDATE food_entries SET image_url = %s WHERE id = %s",
                    (stable_url, entry_id),
                )
                updated += 1

    print(f"Updated {updated} Luna Vita image URL reference(s).")


if __name__ == "__main__":
    main()
