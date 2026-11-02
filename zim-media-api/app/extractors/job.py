"""Subprocess entrypoint. Extraction does not run inside the API server process.

stdin: {"url", "prefixes", "allow_generic", "socket_timeout"}
stdout: {"ok": true, "data": ...} or {"ok": false, "code", "message", "retryable"}
"""

from __future__ import annotations

import json
import os
import sys
import tempfile


def _limit_resources() -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (40, 45))
        # Address-space caps break some allocators; apply only when it succeeds.
        resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, 1_500_000_000))
    except (ImportError, ValueError, OSError):
        return


def main() -> int:
    _limit_resources()
    from app.core.exceptions import APIError
    from app.core.url_validation import install_socket_guard
    from app.extractors.ytdlp import extract_with_ytdlp

    install_socket_guard()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        url = payload["url"]
        with tempfile.TemporaryDirectory(prefix="zim-extract-") as temp_dir:
            data = extract_with_ytdlp(
                url,
                prefixes=list(payload.get("prefixes") or []),
                allow_generic=bool(payload.get("allow_generic")),
                socket_timeout=int(payload.get("socket_timeout") or 15),
                temp_dir=temp_dir,
            )
            leftover = [
                name
                for name in os.listdir(temp_dir)
                if os.path.splitext(name)[1].lower() in {".mp4", ".webm", ".mkv", ".m4a", ".mp3", ".part"}
            ]
            if leftover:
                raise APIError(
                    "EXTRACTION_FAILED",
                    "Extraction tried to store media and was rejected.",
                )
        sys.stdout.write(json.dumps({"ok": True, "data": data}))
        return 0
    except APIError as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                }
            )
        )
        return 2
    except Exception:
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "code": "EXTRACTION_FAILED",
                    "message": "Extraction failed.",
                    "retryable": False,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
