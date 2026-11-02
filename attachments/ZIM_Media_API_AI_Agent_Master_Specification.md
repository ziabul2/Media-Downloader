# ZIM Media API
## AI Agent Master Specification: Architecture, Implementation Plan, and Acceptance Criteria

**Project type:** Public media extraction and direct-download API  
**Architecture:** Hybrid direct URL + redirect + controlled proxy fallback  
**Primary language:** Python  
**Preferred framework:** FastAPI  
**Primary extraction engine:** yt-dlp  
**Hosting:** Provider not selected; design for portable Linux/VPS deployment  
**Primary objective:** Deliver media directly from the original source to the user's device without permanently storing media files on the ZIM server.

---

## 1. Instructions to the AI Agent

You are the lead software architect and implementation engineer for **ZIM Media API**.

Your job is to design, implement, test, document, and prepare a production-deployable API service according to this specification.

### Non-negotiable requirements

1. Prioritize direct downloads from the original media host.
2. Do not download media files to the ZIM server in the normal extraction or direct-delivery workflow.
3. Support direct media URL responses and HTTP redirects.
4. Implement proxy streaming only as a controlled fallback, with strict resource and security limits.
5. Never claim that a URL is directly downloadable until its format, required headers, and delivery constraints have been evaluated.
6. Do not bypass DRM, paywalls, private-account restrictions, authentication controls, or other access controls.
7. Respect applicable copyright law, source-platform terms, and user authorization.
8. Do not expose API secrets, cookies, signed URLs, or sensitive upstream headers in logs.
9. Keep extraction logic separate from FastAPI route handlers.
10. Make the application portable across Linux VPS providers and self-hosted Linux environments.
11. Build incrementally, run tests, and document any incomplete or unsupported functionality.
12. Never silently substitute a lower quality or different format without reporting the actual result to the client.

### Required clients

- Web browsers
- Android applications
- Third-party API developers
- Desktop applications
- Python applications

### Required output formats

- MP4 video
- MP3 audio
- M4A audio
- Original available quality

### Core design principle

ZIM is a **media extraction and delivery API**, not a conventional server-side file downloader. Its default workflow extracts metadata and temporary source references, then lets the client retrieve media from the original source.

---

## 2. Product goals and non-goals

### Goals

- Accept a supported media URL.
- Identify the source platform.
- Extract title, duration, thumbnail, and available formats.
- Normalize format metadata into a stable API schema.
- Let the client select format and quality.
- Generate short-lived download tickets.
- Return a direct URL or redirect the client to the source.
- Use proxy streaming only when direct delivery is not viable and the source permits proxying.
- Support developer authentication, quotas, rate limits, observability, and API documentation.
- Avoid permanent media storage.

### Non-goals

- Hosting a permanent media library.
- DRM circumvention.
- Bypassing paywalls, private content, account restrictions, or platform access controls.
- Guaranteeing extraction from every website.
- Guaranteeing that every source URL works from every client network.
- Pretending that changing a file extension converts its codec or container.
- Using the API server as a general-purpose arbitrary URL proxy.

---

## 3. Recommended technology stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.12+ | Application and workers |
| API framework | FastAPI | REST API and OpenAPI |
| ASGI server | Uvicorn | API serving |
| Extraction | yt-dlp | Metadata and format extraction |
| HTTP client | HTTPX | Controlled upstream HTTP operations |
| Media processing | FFmpeg | Optional merging/conversion |
| Cache and temporary records | Redis | Metadata cache, tickets, rate-limit counters |
| Persistent database | PostgreSQL | API clients, keys, quotas, audit metadata |
| ORM/migrations | SQLAlchemy + Alembic | Database access and schema migrations |
| Reverse proxy | Nginx | TLS termination and request routing |
| Deployment | Docker Compose | Portable deployment |
| Tests | pytest + HTTPX test client | Unit and integration testing |
| Monitoring | Prometheus + Grafana, later phase | Metrics and dashboards |

Do not require a GPU. The primary direct-delivery workflow is not GPU-dependent.

Use dependency versions that are compatible and pinned in a lock file or constraints file. Do not blindly install unpinned latest versions in production.

---

## 4. High-level architecture

```text
Browser / Android / Desktop / Python / Third-party Developer
                         |
                       HTTPS
                         |
                    Nginx Proxy
                         |
                   FastAPI Gateway
                         |
       +-----------------+------------------+
       |                 |                  |
  Authentication   URL Validator      Rate Limiter
       |                 |                  |
       +-----------------+------------------+
                         |
                 Application Services
                         |
          +--------------+---------------+
          |              |               |
    Extractor       Format Selector   Ticket Manager
     Manager              |               |
          |               |               |
       yt-dlp        Normalized Data    Redis
          |
   Source Platform
          |
   Delivery Manager
          |
     +----+---------------------+
     |                          |
 Direct URL / Redirect      Proxy Streaming
     |                          |
     +------------+-------------+
                  |
             User Device
```

### Service responsibilities

- **API Gateway:** Request parsing, authentication, response schemas, API versioning.
- **URL Validator:** Scheme, hostname, DNS, IP, redirect, and destination checks.
- **Extractor Manager:** Selects an approved extractor adapter.
- **yt-dlp Adapter:** Extracts metadata and formats without downloading media.
- **Metadata Normalizer:** Converts extractor-specific output into stable internal models.
- **Format Selector:** Evaluates format, codec, container, quality, audio/video presence, and merge requirements.
- **Ticket Manager:** Creates and validates short-lived opaque download tickets.
- **Delivery Manager:** Chooses direct URL, redirect, or permitted proxy fallback.
- **Proxy Streamer:** Forwards approved upstream media data in chunks and supports Range requests where the upstream supports them.
- **Worker:** Runs extraction in isolated, bounded processes.
- **Redis:** Temporary metadata, ticket records, and rate-limit state.
- **PostgreSQL:** Developer accounts, API key hashes, quotas, usage records, and administrative metadata.

---

## 5. Delivery strategy

The delivery policy must prioritize direct delivery.

### Strategy priority

1. **Direct URL:** Return the upstream media URL when it is safe and usable by the client.
2. **HTTP redirect:** Return a temporary ZIM URL that responds with a redirect to the upstream media URL.
3. **Proxy stream:** Use only when direct delivery is unsuitable, the source permits proxying, and the request passes security and resource checks.
4. **Unsupported:** If none is safe or viable, return a clear structured error. Do not claim success.

### Direct URL response

Example:

```json
{
  "success": true,
  "data": {
    "delivery": "direct",
    "url": "UPSTREAM_SIGNED_MEDIA_URL",
    "expires_in": 900,
    "filename": "example.mp4",
    "format": "mp4"
  }
}
```

The API must not expose this response to unauthenticated callers unless the deployment intentionally provides public access. Signed upstream URLs are sensitive and should be excluded from logs.

### Redirect response

Example:

```http
GET /api/v1/download/{ticket}
```

Response:

```http
HTTP/1.1 302 Found
Location: https://approved-source.example/media
Cache-Control: no-store
Referrer-Policy: no-referrer
```

Use 302 or 303 according to the client workflow. Do not assume the upstream response will have a particular `Content-Disposition` or filename. The upstream host controls the final response.

### Proxy streaming

Use FastAPI `StreamingResponse` or an equivalent streaming response. Use HTTPX streaming mode. Do not read the entire upstream body into memory.

Requirements:

- Enforce allowed source hosts/platform policies.
- Revalidate destination IPs and redirects.
- Apply connection, read, and total timeouts.
- Apply maximum concurrent streams.
- Apply bandwidth and duration limits.
- Close upstream responses when clients disconnect.
- Forward only necessary, allowlisted request headers.
- Do not forward arbitrary client headers.
- Do not forward upstream `Set-Cookie` to clients.
- Do not expose internal upstream error bodies.
- Correctly handle Range requests and 206 responses.
- Preserve relevant headers such as `Content-Type`, `Content-Length`, `Content-Range`, `Accept-Ranges`, and safe `Content-Disposition` values.
- Handle upstream 416 responses correctly.
- Do not claim resumability if the source does not support byte ranges.

Proxy fallback is not a way to bypass source authorization, DRM, geo restrictions, or platform protections.

---

## 6. Media formats and quality

### Normalized format model

Every available format should be normalized to fields similar to:

```json
{
  "format_id": "source-format-id",
  "ext": "mp4",
  "container": "mp4",
  "video_codec": "h264",
  "audio_codec": "aac",
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "audio_bitrate": null,
  "filesize": null,
  "has_video": true,
  "has_audio": true,
  "requires_merge": false,
  "delivery_compatible": true
}
```

Fields may be null when the source does not provide them. Do not fabricate missing values.

### MP4 video

Prefer a progressive MP4 format containing both video and audio. If the best video and audio are separate streams, mark `requires_merge: true`.

Do not return a silent video stream as a complete MP4 download without clearly identifying that it has no audio.

For zero-storage delivery, prefer:
1. Progressive source MP4 with audio and video.
2. Client-side merging in a capable native application or browser using a suitable media-processing implementation.
3. Optional server-side processing only as a separately configured feature.

### M4A audio

Select a compatible M4A audio-only source format when available. Deliver directly when the source permits it.

### MP3 audio

MP3 is a codec/format conversion requirement when the source does not already provide MP3.

Preferred order:
1. Direct MP3 when genuinely available.
2. Client-side conversion using a suitable native or browser media-processing library.
3. Optional server-side FFmpeg conversion as a separately enabled feature.

Never rename M4A/WebM data to `.mp3` without conversion.

### Original quality

“Original quality” means the highest available source quality, not a guarantee of a single combined file.

Return:
- selected video format,
- selected audio format if separate,
- codec/container details,
- whether merging is required,
- source limitations,
- actual delivery strategy.

### yt-dlp selector guidance

Use dynamic format inspection and selection. Example selectors may be used as starting points, but do not assume they are universally valid:

```python
FORMAT_RULES = {
    "mp4_progressive": "best[ext=mp4][vcodec!=none][acodec!=none]",
    "m4a": "bestaudio[ext=m4a]",
    "original": "bestvideo+bestaudio/best",
}
```

The application must inspect the returned formats and handle no-match cases. Avoid selecting a format based only on its extension.

---

## 7. Extraction engine

Extraction must be isolated from HTTP route functions.

### Extraction workflow

1. Receive a URL.
2. Validate URL syntax and scheme.
3. Resolve and validate hostname/IP according to SSRF policy.
4. Identify supported platform or approved generic extractor.
5. Start a bounded extraction job.
6. Run yt-dlp metadata extraction with downloading disabled.
7. Normalize metadata and formats.
8. Store only temporary metadata in Redis.
9. Return an extraction ID and normalized result.

### yt-dlp example

```python
import yt_dlp

def extract_metadata(url: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 15,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "extractor": info.get("extractor_key"),
        "formats": info.get("formats", []),
    }
```

This is a starting example, not a complete production implementation. The agent must add process isolation, URL validation, timeout enforcement, output-size limits, error mapping, and safe logging.

### Worker isolation

Do not execute untrusted extraction work in the public API process.

Run extraction in a separate worker process or isolated job service with:

- Non-root user.
- CPU and memory limits.
- Wall-clock timeout.
- Restricted filesystem.
- No access to application secrets beyond what is explicitly required.
- Restricted network egress.
- Controlled temporary directory.
- No arbitrary shell command construction.
- Concurrency limits.

Use subprocess argument arrays rather than shell interpolation if invoking command-line tools.

### Extractor interface

Create a base interface so additional extractors can be added later:

```python
from typing import Protocol

class Extractor(Protocol):
    def supports(self, url: str) -> bool: ...
    def extract(self, url: str) -> dict: ...
```

Create a registry that selects only approved extractor implementations.

---

## 8. REST API specification

Base URL:

```text
https://api.example.com/api/v1
```

All JSON responses must use a consistent envelope.

### System endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness including required dependencies |
| GET | `/version` | API and extractor versions |
| GET | `/platforms` | Supported platform list |
| GET | `/capabilities` | Supported formats and delivery methods |

### Extraction endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/extract` | Extract metadata and formats |
| GET | `/extract/{extraction_id}` | Retrieve temporary extraction result |
| GET | `/formats/{extraction_id}` | List available formats |
| POST | `/formats/select` | Validate/select a format |

### Download endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/download-link` | Create a temporary download ticket |
| GET | `/download/{ticket}` | Redirect to source |
| GET | `/download/{ticket}/info` | Return ticket metadata without exposing secrets |
| GET | `/stream/{ticket}` | Controlled proxy stream |
| DELETE | `/download/{ticket}` | Revoke ticket |

### Developer endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/developer/keys` | Create API key, authenticated owner only |
| GET | `/developer/usage` | Usage summary |
| GET | `/developer/limits` | Current quota and rate limits |

Never return the plaintext API key after its initial creation. Store only a secure hash, and provide a key rotation/revocation flow.

### Extract request

```http
POST /api/v1/extract
Content-Type: application/json
X-API-Key: YOUR_API_KEY
```

```json
{
  "url": "https://approved-source.example/video",
  "media_type": "video",
  "preferred_format": "mp4",
  "preferred_quality": "1080p"
}
```

### Extract response

```json
{
  "success": true,
  "data": {
    "extraction_id": "ext_example123",
    "platform": "example",
    "title": "Example Video",
    "duration": 320,
    "thumbnail": "https://example-source.example/thumb.jpg",
    "formats": [
      {
        "format_id": "format_a",
        "ext": "mp4",
        "quality": "720p",
        "has_video": true,
        "has_audio": true,
        "requires_merge": false
      },
      {
        "format_id": "format_b",
        "ext": "mp4",
        "quality": "1080p",
        "has_video": true,
        "has_audio": false,
        "requires_merge": true
      }
    ]
  }
}
```

All values are illustrative. Use actual extractor output.

### Download-link request

```http
POST /api/v1/download-link
Content-Type: application/json
X-API-Key: YOUR_API_KEY
```

```json
{
  "extraction_id": "ext_example123",
  "format_id": "format_a",
  "delivery": "auto"
}
```

Supported delivery preferences:
- `auto`
- `direct`
- `redirect`
- `proxy`

The API may reject a requested mode if it is not supported or safe. `auto` should prefer direct, then redirect, then an eligible proxy fallback.

### Download-link response

```json
{
  "success": true,
  "data": {
    "ticket": "opaque-random-ticket",
    "delivery": "redirect",
    "download_url": "https://api.example.com/api/v1/download/opaque-random-ticket",
    "filename": "example-video.mp4",
    "expires_in": 900
  }
}
```

### Error response

```json
{
  "success": false,
  "error": {
    "code": "FORMAT_UNAVAILABLE",
    "message": "The requested format is not available.",
    "retryable": false,
    "request_id": "req_example"
  }
}
```

Recommended error codes:

- `INVALID_URL`
- `UNSUPPORTED_SCHEME`
- `UNSUPPORTED_PLATFORM`
- `BLOCKED_DESTINATION`
- `VIDEO_UNAVAILABLE`
- `PRIVATE_MEDIA`
- `EXTRACTION_FAILED`
- `EXTRACTION_TIMEOUT`
- `FORMAT_UNAVAILABLE`
- `MEDIA_URL_EXPIRED`
- `DELIVERY_UNAVAILABLE`
- `PROXY_NOT_ALLOWED`
- `RATE_LIMIT_EXCEEDED`
- `QUOTA_EXCEEDED`
- `INVALID_TICKET`
- `TICKET_EXPIRED`
- `UPSTREAM_ERROR`

---

## 9. Ticket and temporary metadata design

Use cryptographically secure random opaque tickets. Do not encode raw media URLs or credentials into ticket strings.

Example temporary Redis record:

```json
{
  "ticket_id": "internal-id",
  "owner_key_id": "developer-id",
  "source_url": "SENSITIVE_UPSTREAM_URL",
  "required_headers": {
    "User-Agent": "approved-value"
  },
  "format_id": "format_a",
  "filename": "example.mp4",
  "delivery": "redirect",
  "created_at": 1793650000,
  "expires_at": 1793650900
}
```

This record is illustrative. Store only fields required for delivery. Encrypt sensitive values where appropriate, restrict Redis access, and never log them.

Suggested initial TTLs:
- Metadata cache: 5 minutes.
- Download ticket: 15 minutes.
- API usage counters: configured daily/monthly windows.

These are configuration defaults, not guarantees about source URL lifetime. If the source URL expires first, invalidate the ticket and require re-extraction.

Ticket requirements:
- Cryptographically secure generation.
- Short expiry.
- Bound to an API key or permitted client identity where practical.
- One-time use should be configurable, not mandatory, because browsers and download managers may retry or make Range requests.
- Revocation support.
- No sensitive URL in the public ticket.
- Do not expose ticket values in analytics or logs.

---

## 10. Security requirements

Security is a release blocker.

### SSRF protection

The API must not become an arbitrary URL fetcher.

- Permit only HTTP/HTTPS where required.
- Reject localhost and loopback.
- Reject private, link-local, multicast, reserved, and unspecified IP ranges.
- Reject cloud metadata destinations.
- Validate DNS results and the actual connected destination.
- Revalidate every redirect.
- Defend against DNS rebinding.
- Use an egress firewall or controlled outbound proxy as defense in depth.
- Do not trust a hostname merely because its initial DNS result was public.
- Avoid arbitrary user-supplied headers.
- Restrict supported hosts/platforms where practical.

### API authentication and abuse controls

- API key authentication for developer clients.
- Hash API keys at rest.
- Key rotation and revocation.
- Per-key and per-IP rate limits.
- Request quotas.
- Maximum extraction concurrency.
- Maximum URL length.
- Request body size limits.
- Extraction and upstream timeouts.
- Abuse detection and audit events.

### Secrets and privacy

- Store secrets in environment variables or a secrets manager.
- Never commit `.env`.
- Never log API keys, cookies, authorization headers, signed URLs, or ticket values.
- Redact sensitive query parameters.
- Restrict access to worker processes.
- Use HTTPS.
- Configure CORS only for known browser origins. CORS is not authentication.
- Define log retention and data deletion policies.

### Content and platform rules

- Only process media the caller is authorized to access and download.
- Respect platform terms and applicable law.
- Do not implement DRM circumvention or authentication bypass.
- Do not bypass private-account restrictions or paywalls.
- Do not evade geographic or other access restrictions.
- Provide clear errors when media is unavailable or access is denied.

---

## 11. Client integration requirements

### Browser

- Use `fetch()` for JSON extraction and ticket creation.
- Use ordinary browser navigation or a download link for redirect delivery.
- Do not fetch large media blobs into JavaScript memory by default.
- Remember that reading cross-origin media bytes with `fetch()` requires source CORS permission.
- Do not expose long-lived API secrets in public frontend code. Use a backend-for-frontend or restricted public-client credentials where appropriate.

Example:

```javascript
async function extract(url, apiKey) {
  const response = await fetch(
    "https://api.example.com/api/v1/extract",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey
      },
      body: JSON.stringify({
        url,
        media_type: "video",
        preferred_format: "mp4"
      })
    }
  );

  if (!response.ok) {
    throw new Error(`Extraction failed: ${response.status}`);
  }

  return response.json();
}
```

### Android

Recommended:
- Kotlin.
- OkHttp or Retrofit for API calls.
- Android DownloadManager for normal URL downloads.
- Native storage/MediaStore integration.
- Native merging/conversion only where needed and permitted.

Do not route ordinary media bytes through the Android app's API response parser.

### Desktop

Support the same REST contract. Possible clients:
- Python + PySide6
- Electron
- Tauri

### Python

Provide a documented Python example and, later, an official SDK.

```python
import requests

BASE_URL = "https://api.example.com/api/v1"

response = requests.post(
    f"{BASE_URL}/extract",
    headers={"X-API-Key": "YOUR_API_KEY"},
    json={
        "url": "https://approved-source.example/video",
        "media_type": "video",
        "preferred_format": "mp4"
    },
    timeout=30
)

response.raise_for_status()
result = response.json()
print(result)
```

---

## 12. Database design

PostgreSQL should store developer and service metadata, not media files.

Suggested tables:

### `developers`
- `id`
- `name`
- `email`
- `status`
- `created_at`

### `api_keys`
- `id`
- `developer_id`
- `key_hash`
- `key_prefix`
- `status`
- `created_at`
- `last_used_at`
- `revoked_at`

### `usage_events`
- `id`
- `developer_id`
- `api_key_id`
- `endpoint`
- `status_code`
- `duration_ms`
- `delivery_method`
- `created_at`

Do not store raw media URLs or sensitive upstream headers in usage events.

### `quota_plans`
- `id`
- `name`
- `requests_per_minute`
- `requests_per_day`
- `max_concurrent_extractions`
- `max_concurrent_streams`

Use Redis for short-lived extraction records and tickets. Do not use PostgreSQL as a media-file store.

---

## 13. Recommended project structure

```text
zim-media-api/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   └── v1/
│   │       ├── health.py
│   │       ├── extract.py
│   │       ├── formats.py
│   │       ├── download.py
│   │       ├── stream.py
│   │       ├── platforms.py
│   │       └── developer.py
│   ├── core/
│   │   ├── security.py
│   │   ├── url_validation.py
│   │   ├── rate_limit.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   ├── services/
│   │   ├── extraction.py
│   │   ├── format_selector.py
│   │   ├── download_manager.py
│   │   ├── delivery_manager.py
│   │   └── ticket_manager.py
│   ├── extractors/
│   │   ├── base.py
│   │   ├── ytdlp.py
│   │   └── registry.py
│   ├── streaming/
│   │   ├── proxy.py
│   │   └── range_handler.py
│   ├── database/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── repositories.py
│   ├── schemas/
│   │   ├── extraction.py
│   │   ├── download.py
│   │   └── response.py
│   └── worker.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── security/
├── deployment/
│   ├── nginx.conf
│   └── docker-compose.yml
├── scripts/
│   ├── doctor.py
│   └── update_extractors.py
├── .env.example
├── .gitignore
├── Dockerfile
├── requirements.txt
├── README.md
├── SECURITY.md
└── LICENSE
```

The agent may improve this structure if there is a clear engineering reason, but must preserve separation of concerns.

---

## 14. Deployment strategy

Hosting provider is undecided. Keep deployment portable.

### Initial VPS profile

Suggested starting point, to be validated with load tests:
- 2 vCPU
- 4 GB RAM
- 30–50 GB SSD
- Debian 13 or supported Ubuntu LTS
- Docker and Docker Compose
- Public domain and HTTPS

A self-hosted Linux server may be used for development or production if it has reliable connectivity, public reachability, security maintenance, and sufficient capacity.

Serverless platforms are not the first choice because extraction subprocesses and streaming workloads may conflict with execution limits.

### Docker services

The deployment should contain:
- `api`
- `worker`
- `redis`
- `postgres`
- `nginx`

Use:
- Non-root containers.
- Internal Docker networks for Redis and PostgreSQL.
- Persistent database volume.
- Health checks.
- Resource limits.
- Environment-based secrets.
- Restart policies.
- Log rotation.
- Explicit outbound network policy.

Do not expose Redis or PostgreSQL publicly.

The following is a topology illustration, not a complete production Compose file:

```yaml
services:
  api:
    build: .
    restart: unless-stopped
    depends_on:
      - redis
      - postgres

  worker:
    build: .
    command: python -m app.worker
    restart: unless-stopped
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    restart: unless-stopped

  postgres:
    image: postgres:17-alpine
    restart: unless-stopped
```

The implementation agent must complete the configuration with environment variables, volumes, networks, health checks, resource limits, and Nginx.

---

## 15. Observability and operations

Expose safe metrics:
- Request count by endpoint and status.
- Extraction success/failure rate.
- Extraction latency.
- Queue length.
- Worker CPU/memory.
- Active proxy streams.
- Direct vs redirect vs proxy delivery counts.
- Upstream failure categories.
- Cache hit ratio.
- Rate-limit events.
- API quota usage.

Never use media URLs, API keys, cookies, signed tokens, or ticket values as metric labels.

Create:
- `/health` for liveness.
- `/ready` for dependency readiness.
- Structured JSON logs with request IDs.
- Redaction filters.
- Log retention policy.
- Alerts for worker failures, queue buildup, high error rates, and resource exhaustion.

A key product metric is **Direct Delivery Success Rate**: the percentage of eligible download requests completed without media bytes passing through ZIM infrastructure.

---

## 16. Development phases

### Phase 1 — Core API
- FastAPI project setup.
- Configuration and environment handling.
- API versioning.
- Health/readiness/version endpoints.
- Request/response schemas.
- Standard errors.
- OpenAPI documentation.

**Exit criteria:** API starts reliably and passes basic endpoint tests.

### Phase 2 — Extraction
- yt-dlp adapter.
- URL validation.
- Metadata extraction without media download.
- Format normalization.
- Platform registry.
- Isolated worker execution.
- Timeout and concurrency limits.

**Exit criteria:** Authorized test URLs return accurate metadata and formats without saving media files.

### Phase 3 — Direct delivery
- Format selection.
- Temporary extraction cache.
- Secure download tickets.
- Direct URL response.
- Redirect endpoint.
- Ticket expiration/revocation.

**Exit criteria:** A client can download an eligible test media item directly from its source, with no media bytes routed through ZIM.

### Phase 4 — Format handling
- MP4 progressive selection.
- Separate audio/video detection.
- M4A direct delivery.
- MP3 availability and conversion requirements.
- Original-quality metadata.
- Explicit merge requirements.
- Optional client-side processing guidance.

**Exit criteria:** API never mislabels formats or claims that separate streams are a complete file.

### Phase 5 — Proxy fallback
- HTTPX streaming.
- Range forwarding.
- Client disconnect handling.
- Upstream timeout handling.
- Concurrency and bandwidth limits.
- Safe header filtering.
- Source permission checks.

**Exit criteria:** Authorized test streams work without full-file buffering and pass Range tests where supported.

### Phase 6 — Developer platform and security
- API key creation/rotation/revocation.
- Key hashing.
- Rate limits and quotas.
- SSRF protections.
- Audit events.
- Developer usage endpoint.
- Security tests.

**Exit criteria:** Security test suite passes and abusive requests are bounded.

### Phase 7 — Production deployment
- Dockerfiles.
- Docker Compose.
- Nginx.
- TLS instructions.
- Database migrations.
- Backup/restore for service metadata.
- Monitoring.
- Load and failure testing.
- Deployment and operations documentation.

**Exit criteria:** Clean deployment from documented instructions on a supported Linux VPS.

---

## 17. Testing and acceptance criteria

The project is not complete until the following are tested.

| Test | Expected result |
|---|---|
| Health endpoint | Returns healthy status |
| Readiness endpoint | Checks required dependencies |
| Valid extraction | Returns normalized metadata |
| Metadata-only behavior | No media file is saved |
| Direct delivery | Media bytes do not pass through ZIM |
| Redirect delivery | Correct 302/303 and no-store behavior |
| Expired ticket | Structured expiry error |
| Revoked ticket | Access denied |
| Invalid URL | Rejected |
| Unsupported scheme | Rejected |
| Localhost/private IP | Blocked |
| DNS rebinding/redirect | Destination revalidated or blocked |
| MP4 progressive | Audio/video presence accurately reported |
| Separate streams | Merge requirement reported |
| M4A | Correct source format reported |
| MP3 | Actual MP3 or explicit conversion requirement |
| Original quality | Actual available streams reported |
| Proxy streaming | Chunked, bounded, no full buffering |
| Range request | Correct 206/416 behavior where upstream supports it |
| Client disconnect | Upstream connection closed |
| Rate limit | Excessive requests rejected |
| Worker timeout | Job terminated and error normalized |
| Log redaction | No secrets or signed URLs in logs |
| Storage audit | No permanent media files created |

Use owned, licensed, or explicitly authorized test media. Avoid tests that depend on bypassing platform protections.

---

## 18. Important technical limitations

1. **Source URL portability:** Some signed media URLs are tied to an IP, cookie, user-agent, or other headers. A URL extracted on the VPS may not work from a phone. Detect this where possible and report the limitation. Proxy only when authorized and permitted.
2. **MP3 conversion:** A source M4A or WebM stream is not MP3. Conversion consumes client or server CPU.
3. **Original quality:** The best video and audio may be separate streams. Original quality may require merging.
4. **Browser CORS:** Browser navigation to a URL is different from JavaScript reading media bytes with `fetch()`. Cross-origin byte access requires appropriate CORS permission from the source.
5. **Storage vs bandwidth:** Direct delivery saves ZIM media bandwidth and storage. Proxy delivery consumes ZIM bandwidth even if it does not permanently store the file.
6. **Platform reliability:** Extractor compatibility changes as source websites change. Build version monitoring and update procedures.
7. **No universal guarantee:** Some sources are unsupported or inaccessible. Return accurate errors instead of promising universal compatibility.

---

## 19. Initial configuration

Create `.env.example` with documented placeholders, for example:

```dotenv
APP_NAME=ZIM Media API
APP_ENV=development
APP_VERSION=0.1.0
API_PREFIX=/api/v1

DATABASE_URL=postgresql+psycopg://zim:change-me@postgres:5432/zim_media
REDIS_URL=redis://redis:6379/0

API_KEY_REQUIRED=true
DEFAULT_TICKET_TTL_SECONDS=900
METADATA_CACHE_TTL_SECONDS=300

EXTRACTION_TIMEOUT_SECONDS=45
MAX_CONCURRENT_EXTRACTIONS=2
MAX_CONCURRENT_STREAMS=5

PROXY_ENABLED=false
MAX_PROXY_DURATION_SECONDS=1800
MAX_PROXY_BYTES=1073741824

LOG_LEVEL=INFO
```

These are development defaults. Validate all configuration values at startup. Production secrets must be generated securely and must never use the example credentials.

Proxy should be disabled until its SSRF, authorization, range, resource, and egress controls are implemented and tested.

---

## 20. Agent implementation workflow

Follow this sequence:

1. Inspect the repository and existing runtime before changing files.
2. Write a concise implementation plan and identify assumptions.
3. Create the project skeleton and configuration.
4. Implement schemas, errors, health endpoints, and tests.
5. Implement URL validation and SSRF protections before enabling extraction.
6. Implement isolated yt-dlp metadata extraction.
7. Implement format normalization and selection.
8. Implement Redis metadata records and secure download tickets.
9. Implement direct URL and redirect delivery.
10. Add proxy streaming only after its security and resource controls are tested.
11. Add API-key management and quotas.
12. Add Docker, Nginx, database migrations, and deployment documentation.
13. Run formatting, linting, type checks, unit tests, integration tests, and security tests.
14. Report exactly what works, what is incomplete, and how to run it.

### Engineering standards

- Use type hints.
- Use Pydantic request/response models.
- Use async endpoints for asynchronous I/O.
- Do not block the event loop with synchronous extraction.
- Use bounded worker processes for extraction.
- Use dependency injection for services.
- Keep routes thin.
- Keep secrets out of source control.
- Add tests for every security-sensitive behavior.
- Document all configuration variables.
- Pin dependencies.
- Do not create fake successful responses or placeholder implementations presented as production-ready.
- If a feature cannot be safely implemented, disable it and explain why.

---

## 21. Required deliverables

The completed project must include:

1. Working FastAPI application.
2. Isolated yt-dlp extraction service.
3. Normalized media metadata and format selector.
4. Direct URL delivery.
5. HTTP redirect delivery.
6. Secure temporary download tickets.
7. Optional, guarded proxy streaming with Range support.
8. MP4, MP3, M4A, and original-quality handling with honest capability reporting.
9. API-key management and rate limiting.
10. Redis and PostgreSQL integration.
11. Docker deployment configuration.
12. Nginx and HTTPS setup documentation.
13. OpenAPI/Swagger documentation.
14. Python and JavaScript client examples.
15. Android integration guide.
16. Automated tests, including SSRF and log-redaction tests.
17. README with local setup and deployment steps.
18. Operations, backup, upgrade, and troubleshooting documentation.

---

## 22. Definition of done

ZIM Media API is ready for its first production release only when:

- A clean Linux environment can deploy it using the documented steps.
- The API extracts metadata without downloading media to permanent server storage.
- Direct delivery is the default for eligible media.
- Redirect delivery works with secure temporary tickets.
- Proxy is disabled by default until its safety controls pass tests.
- Format and merge requirements are accurately represented.
- API keys, quotas, and rate limits work.
- SSRF and sensitive-log tests pass.
- No secrets are committed.
- All documented endpoints have tests.
- The README explains supported behavior and limitations.
- The agent provides a final implementation report with test results and known limitations.

**Final product principle:** Keep the ZIM server responsible for extraction, authorization, metadata, and delivery coordination. Let the original media host deliver the media bytes directly to the user's device whenever technically and legally possible.
