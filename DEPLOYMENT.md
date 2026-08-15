# R4S deployment

The ARM64 images are published to GHCR after every push to `master`.
The deployment stack includes Watchtower, which checks every five minutes and
automatically updates only the frontend and backend containers. PostgreSQL is
not opted in to automatic updates.

## First installation or configuration recovery

Run these commands in `/mnt/docker_data/nano` on the R4S:

```sh
wget -O compose.yaml https://raw.githubusercontent.com/shaoqi2002/nano/master/compose.deploy.yaml
docker compose --env-file .env.production -f compose.yaml config
docker compose --env-file .env.production -f compose.yaml up -d
```

The backend and Watchtower use public DNS servers explicitly because Tailscale
may replace the host resolver with `100.100.100.100`, which Docker's embedded
resolver cannot always reach from a bridge network.

## Web research settings

Requests that include a Tavily API key can use both quick web search and Tavily
Research. Deep research runs as an asynchronous Tavily task that is polled by
the backend. The production defaults allow 180 seconds for completion, poll
every 2 seconds, and cap the report passed back to the chat model at 30,000
characters. Override `DEEP_RESEARCH_TIMEOUT_SECONDS`,
`DEEP_RESEARCH_POLL_INTERVAL_SECONDS`, or
`DEEP_RESEARCH_MAX_CONTENT_LENGTH` in `.env.production` when needed.

Focused source verification uses Tavily Extract after search. By default it
accepts up to 5 URLs, returns at most 20,000 characters across the selected
sources, and allows 45 seconds per extraction request. These limits can be
changed with `WEB_EXTRACT_MAX_URLS`, `WEB_EXTRACT_MAX_CONTENT_LENGTH`, and
`WEB_EXTRACT_TIMEOUT_SECONDS`.

## Backblaze B2 document storage

The document library stores only metadata in PostgreSQL. Original files are
kept in a private Backblaze B2 bucket through its S3-compatible API. Create a
bucket-restricted application key with read and write access, then add the
following values to `.env.production`:

```sh
OBJECT_STORAGE_ENDPOINT_URL=https://s3.us-west-000.backblazeb2.com
OBJECT_STORAGE_REGION=us-west-000
OBJECT_STORAGE_ACCESS_KEY_ID=your-key-id
OBJECT_STORAGE_SECRET_ACCESS_KEY=your-application-key
OBJECT_STORAGE_BUCKET=your-bucket-name
DOCUMENT_MAX_BYTES=26214400
```

Use the exact endpoint displayed on the B2 bucket page; the `us-west-000`
value above is only a placeholder. Keep the bucket private. The application
key is a server secret and must never be placed in a frontend environment
variable or committed to Git.

The reader supports PDF, DOCX, Markdown, plain text, CSV, JSON, log files, and
common raster images. Uploads are limited to 25 MiB by default. PostgreSQL
tables are created automatically when the backend starts.

The current Nano application has no user account or document authorization
layer. Keep port 8088 behind the LAN, Tailscale, or another authenticated
reverse proxy. Anyone who can reach the application can otherwise upload,
download, and delete documents.

## Verification

```sh
docker inspect nano-backend-1 --format 'DNS={{json .HostConfig.Dns}}'
docker exec nano-backend-1 python -c "import socket; print(socket.gethostbyname('api.deepseek.com'))"
docker logs --tail 100 nano-watchtower-1
```
