# Luna Vault

## Generate, Manipulate, Search and Store images of your choice using LLMs.

Luna Vault is an AI-powered, private image library that runs locally. Its Ollama
vision model analyzes every upload automatically, creates a concise caption and
searchable tags, and stores that metadata in PostgreSQL. FastMCP makes the indexed
collection available to AI assistants of your choice (ChatGPT here) for fast search and safe image-management
operations without repeatedly opening every original image.

The Streamlit interface lets you upload, search, view, download, hide, restore,
and delete images. Image data, metadata, and AI models persist in Docker volumes,
while the password-protected hidden vault stays separate from normal galleries
and searches.

<p align="center">
  <img src="docs/assets/luna-vault-ai-assistant.png" alt="AI assistant querying Luna Vault alongside its image gallery" width="900">
</p>

An MCP-connected AI assistant can query Luna Vault's generated captions and tags,
answer collection-level questions, and return matching filenames without visually
reprocessing every original image.

Luna Vault is also well suited to bulk image manipulation and editing workflows.
Its MCP tools let an AI assistant find and act on groups of images while keeping
the stored files and their searchable metadata synchronized.

<p align="center">
  <img src="docs/assets/luna-vault-gallery.png" alt="Searchable Luna Vault image gallery" width="720">
</p>

The main gallery provides filename search, pagination, AI-generated captions and
tags, full-size viewing, downloads, and deletion controls.

<p align="center">
  <img src="docs/assets/luna-vault-hidden-gallery.png" alt="Password-protected Luna Vault hidden gallery" width="720">
</p>

The hidden vault keeps private images behind a password and supports adding,
viewing, downloading, restoring, searching, and deleting them separately.

<p align="center">
  <img src="docs/assets/luna-vault-hidden-example.png" alt="Example image stored in Luna Vault's hidden gallery" width="300">
</p>

An example image stored in the password-protected hidden gallery. yah... i know...

## Run

Optionally set `POSTGRES_PASSWORD`, then build and start:

```sh
docker compose up --build
```

The first run downloads the configured vision model. Open Luna Vault at
<http://127.0.0.1:18501>. The Hidden Images tab lets you create a password and an
exactly 8-digit reset PIN; both are salted and hashed in PostgreSQL.

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


## Database UI

Adminer is available at <http://127.0.0.1:19080> after starting the stack. Use:

- System: `PostgreSQL`
- Server: `postgres`
- Username: `lunavault`
- Password: your `POSTGRES_PASSWORD`, or `lunavault-dev` when unset
- Database: `lunavault`

Adminer is bound to localhost and reaches PostgreSQL only through the private Luna Vault network. The database port itself remains unavailable from the host.

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
