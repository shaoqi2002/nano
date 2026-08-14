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
resolver cannot always reach from a bridge network. The backend also contains
the currently advertised `api.deepseek.com` edge addresses in `extra_hosts` as
a persistent fallback. If DeepSeek changes all of these addresses, refresh the
entries with the results of `nslookup api.deepseek.com` on the R4S host.

## Verification

```sh
docker inspect nano-backend-1 --format 'DNS={{json .HostConfig.Dns}}'
docker exec nano-backend-1 python -c "import socket; print(socket.gethostbyname('api.deepseek.com'))"
docker logs --tail 100 nano-watchtower-1
```
