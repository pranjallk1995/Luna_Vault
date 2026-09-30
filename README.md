# Luna Vault

A minimal container foundation for a personal image vault:

- PostgreSQL with pgvector, reachable only from other Compose services.
- A minimal MCP service at `http://mcp:8000/mcp` on the internal Compose network.
- A Streamlit upload UI exposed only on the host's loopback interface.
- A persistent `image_data` volume shared read/write with the UI and read-only with MCP.

## Run

Optionally set `POSTGRES_PASSWORD` in your shell, then build and start the stack:

```sh
docker compose up --build
```

Open the upload UI at <http://127.0.0.1:18501>.

Stop the stack with:

```sh
docker compose down
```

The UI's restrained dark theme is configured in `ui/.streamlit/config.toml` and copied into the UI image with the application source.

## Development

The local `ui/` and `mcp/` directories are bind-mounted at `/workspace/ui` and `/workspace/mcp` respectively. Streamlit watches its source and reloads the UI when files in `ui/` change.

The MCP server does not have hot reload configured. After editing files in `mcp/`, restart only that service to load the changes:

```sh
docker compose restart mcp
```

Named volumes are retained by default. This foundation stores uploads and lets MCP clients list them; image indexing and vector search are intentionally not implemented yet.
