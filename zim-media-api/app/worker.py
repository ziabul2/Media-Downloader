"""Queue worker. Run as `python -m app.worker` when EXTRACTION_BACKEND=queue.

The API process only enqueues. This process performs yt-dlp metadata extraction.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time

from app.config import load_settings
from app.core.exceptions import APIError
from app.core.logging import configure_logging
from app.core.url_validation import install_socket_guard
from app.extractors.ytdlp import extract_with_ytdlp

logger = logging.getLogger("zim.worker")


def run_once(client, settings) -> bool:
    item = client.brpop("zim:jobs", timeout=5)
    if not item:
        return False
    _, raw = item
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    job = json.loads(raw)
    job_id = str(job.get("id") or "")
    try:
        with tempfile.TemporaryDirectory(prefix="zim-worker-") as temp_dir:
            data = extract_with_ytdlp(
                job["url"],
                prefixes=list(job.get("prefixes") or settings.extractor_prefixes()),
                allow_generic=bool(job.get("allow_generic")),
                socket_timeout=int(job.get("socket_timeout") or settings.extraction_socket_timeout_seconds),
                temp_dir=temp_dir,
            )
        body = {"ok": True, "data": data}
    except APIError as exc:
        body = {"ok": False, "code": exc.code, "message": exc.message, "retryable": exc.retryable}
    except Exception:
        logger.error("worker_job_failed")
        body = {"ok": False, "code": "EXTRACTION_FAILED", "message": "Extraction failed.", "retryable": False}
    if job_id:
        client.set(f"zim:job:{job_id}", json.dumps(body), ex=120)
    return True


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    if not settings.redis_url:
        raise SystemExit("REDIS_URL is required for the worker")
    import redis

    install_socket_guard()
    client = redis.Redis.from_url(settings.redis_url)
    logger.info("worker_started")
    while True:
        try:
            run_once(client, settings)
        except Exception:
            logger.error("worker_loop_error")
            time.sleep(1)


if __name__ == "__main__":
    main()
