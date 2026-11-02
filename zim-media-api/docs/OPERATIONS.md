# Operations

## What is stored

PostgreSQL stores developers, hashed API keys, quotas, and usage events. Usage events do not include media URLs or ticket values.

Redis stores extraction records and download tickets. Default lifetimes are 5 minutes and 15 minutes. Losing Redis invalidates tickets; that is expected. Do not persist media in Redis.

No volume is a media library. If a worker temporary directory contains `mp4`, `m4a`, `webm`, or `mkv` after a job, treat it as a bug and stop the worker.

## Backup

Dump only Postgres:

```bash
docker compose exec postgres pg_dump -U zim zim_media > zim_meta.sql
```

Restore into an empty database, then start the API. Tickets are not part of the backup.

## Upgrade

1. Pin the new yt-dlp release in `requirements.txt`. Run `python scripts/update_extractors.py` and the test suite.
2. Rebuild the API and worker images together so they share one extractor version.
3. Apply Alembic before traffic: the image entrypoint runs `alembic upgrade head` when `AUTO_CREATE_SCHEMA=false`.
4. Roll the worker first, then the API.

## Health

- `GET /health` — process is up.
- `GET /ready` — database answers, and Redis answers when `REDIS_REQUIRED=true`.
- `GET /metrics` — counters only. Labels are endpoint, status, and delivery method.

Alert on worker restarts, `/ready` failures, a rising `EXTRACTION_FAILED` rate, and proxy stream concurrency if proxy is ever enabled.

## Direct delivery success

Count download-link responses whose `delivery` is `direct` or `redirect`. Those requests did not move media bytes through ZIM. Proxy responses did. That ratio is the product metric.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `BLOCKED_DESTINATION` | URL resolves to a private, loopback, or metadata address |
| `UNSUPPORTED_PLATFORM` | Extractor is not on the allow list, or the URL is generic |
| `PRIVATE_MEDIA` | Login, membership, or DRM. Do not add cookies to bypass it |
| `EXTRACTION_TIMEOUT` | Worker killed the job at `EXTRACTION_TIMEOUT_SECONDS` |
| `TICKET_EXPIRED` | Re-extract. Source URLs often die before the ticket TTL |
| Redirect works on the server and fails on a phone | Signed URL is bound to an IP or header. The ticket constraint says so |
| `PROXY_NOT_ALLOWED` | Expected. Proxy ships disabled |

## Network

Block outbound traffic from the API and worker to RFC1918, link-local, and `169.254.169.254` at the firewall as well. The application checks DNS and the connected address; the firewall is the second layer.
