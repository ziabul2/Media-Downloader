# ZIM Media API

ZIM extracts metadata for a public media URL and hands the client a direct URL or a short-lived redirect. The server does not keep the file.

Proxy streaming, server-side merge, and server-side MP3 conversion ship **disabled**. A missing MP3 is reported as a conversion requirement. A video-only stream is reported as `requires_merge`. Neither is disguised as a finished file.

## What you can call

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Database, and Redis when required |
| GET | `/version` | API and yt-dlp versions |
| GET | `/platforms` | Enabled platforms |
| GET | `/capabilities` | Formats and delivery methods |
| POST | `/api/v1/extract` | Metadata and formats |
| GET | `/api/v1/extract/{id}` | Cached extraction |
| GET | `/api/v1/formats/{id}` | Formats for an extraction |
| POST | `/api/v1/formats/select` | Check one format |
| POST | `/api/v1/download-link` | Create a ticket |
| GET | `/api/v1/download/{ticket}` | 302 to the source |
| GET | `/api/v1/download/{ticket}/info` | Ticket metadata, no secrets |
| DELETE | `/api/v1/download/{ticket}` | Revoke |
| GET | `/api/v1/stream/{ticket}` | Proxy, only if enabled |
| POST | `/api/v1/developer/keys` | Create a key (owner only, shown once) |
| GET | `/api/v1/developer/usage` | Usage summary |
| GET | `/api/v1/developer/limits` | Quota |

Interactive docs: `/docs`.

Send `X-API-Key` on JSON routes. Browser download links use the unguessable ticket and do not need the header.

## Local run

Python 3.10+ is enough to develop. The container image is Python 3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/doctor.py
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Development creates a local owner key on first boot and stores only its hash. The console at `/` can use it. Set `APP_ENV=production` and that endpoint turns off.

Defaults: SQLite at `./data/zim.db`, in-process ticket store if Redis is down, proxy off. Production refuses the example pepper, SQLite, and a missing Redis URL.

```bash
.venv/bin/pytest
```

## Docker

```bash
cp .env.example .env
# Generate API_KEY_PEPPER and POSTGRES_PASSWORD. Put the same password in DATABASE_URL.
# Keep PROXY_ENABLED=false until the proxy tests are part of your release check.
cd deployment
POSTGRES_PASSWORD='the-same-password' docker compose up --build
```

Redis and Postgres stay on an internal network. Nginx publishes port 80. Put TLS on Nginx before any public traffic; a commented 443 block is in `deployment/nginx.conf`.

The API container runs `alembic upgrade head` when `AUTO_CREATE_SCHEMA=false`. The worker runs `python -m app.worker` and is the process that calls yt-dlp in queue mode. Local mode shells out to `python -m app.extractors.job` instead, still outside the request process.

## Clients

- [examples/python_client.py](examples/python_client.py)
- [examples/browser_extract.js](examples/browser_extract.js)
- [docs/ANDROID.md](docs/ANDROID.md)

Do not read the media into JavaScript memory. Open the ticket URL. Cross-origin `fetch()` of the bytes only works when the source sends CORS, which most hosts do not.

## Formats

- **MP4:** progressive file with audio and video when one exists. Otherwise the API says a merge is required and will not return the silent track as a complete download.
- **M4A:** a real M4A (or it says the source extension it actually found).
- **MP3:** a real MP3, or `conversion_required: true` plus the source audio. The bytes are not renamed.
- **Original:** the best single file, plus the best separate video and audio when those are higher. Highest quality may be two streams.

`delivery: auto` prefers a direct URL, then a redirect ticket. Both are refused for playlists, live streams, HLS/DASH manifests, and merge/conversion jobs.

## Limits

- Some signed URLs only work with a user-agent, referer, or the server's IP. The ticket includes `constraints` when that is visible. A phone can still fail. That is reported, not patched with a silent proxy.
- Platform HTML changes. Bump the yt-dlp pin on purpose (`scripts/update_extractors.py`).
- Enabled platforms are an allow list. Arbitrary sites hit `UNSUPPORTED_PLATFORM`.
- DRM, private videos, paywalls, and geo blocks return errors. There is no cookie jar and `geo_bypass` is off.

## Operations

Backup, upgrades, and alerts: [docs/OPERATIONS.md](docs/OPERATIONS.md).

Security model: [SECURITY.md](SECURITY.md).
