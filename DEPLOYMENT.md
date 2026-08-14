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

## Verification

```sh
docker inspect nano-backend-1 --format 'DNS={{json .HostConfig.Dns}}'
docker exec nano-backend-1 python -c "import socket; print(socket.gethostbyname('api.deepseek.com'))"
docker logs --tail 100 nano-watchtower-1
```
