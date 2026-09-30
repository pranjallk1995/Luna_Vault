# Luna Vault

Luna Vault is a private, local image vault with:

- PostgreSQL metadata and full-text/tag indexes.
- A FastMCP server with image lifecycle and metadata search tools.
- Local Ollama vision analysis accelerated by an NVIDIA GPU when available.
- A Streamlit upload, view, and delete interface.
- Persistent Docker volumes for database data, images, and Ollama models.

## Vision model

The default model is `qwen2.5vl:7b`. Override it before starting the stack:

```sh
export VISION_MODEL=qwen2.5vl:7b
```

Ollama runs only on the private Compose network. No API key or external image service is used. Download the model once into the persistent `ollama_data` volume before starting the full stack:

```sh
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5vl:7b
```

## Run

Optionally set `POSTGRES_PASSWORD`, then build and start:

```sh
docker compose up --build
```

The first run downloads the configured vision model. Open Luna Vault at <http://127.0.0.1:18501>.

Check GPU use while analysis is active:

```sh
docker compose exec ollama ollama ps
nvidia-smi
```

If NVIDIA passthrough is unavailable, remove `gpus: all` from the Ollama service to use the CPU fallback. Captioning will still work but will be slower.

## Metadata and search

Every add, upload, or replacement is analyzed before it is committed. The generated caption, normalized tags, content hash, model name, and timestamps are stored in PostgreSQL. Deletion removes the file and its metadata consistently.

The MCP tool:

```text
search_images(
  query: str = "",
  tags: list[str] | None = None,
  match_all_tags: bool = False,
  limit: int = 50,
  offset: int = 0
)
```

returns `{query, normalized_query, count, results[]}`, where each result contains `name`, `caption`, `tags`, and `updated_at`. Search reads the metadata index and never opens original images. PostgreSQL uses a generated weighted `tsvector` with a GIN index for English caption/tag full-text search and a second GIN index for tag array queries.

Run or resume an idempotent metadata backfill through the MCP `backfill_metadata` tool after importing images outside the normal ingestion flow.

## Development

The UI source is bind-mounted at `/workspace/ui` and Streamlit reloads on edits. The MCP source is bind-mounted at `/workspace/mcp`; restart MCP after editing:

```sh
docker compose restart mcp
```

The dark theme is in `ui/.streamlit/config.toml`. Stop the stack with `docker compose down`; named volumes remain.

