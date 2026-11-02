"""Check the local runtime without printing secrets."""

from __future__ import annotations

import importlib.metadata
import shutil
import sys


def main() -> int:
    print(f"python {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        print("python is older than 3.10")
        return 1
    for package in ("fastapi", "yt_dlp", "httpx", "sqlalchemy"):
        try:
            if package == "yt_dlp":
                import yt_dlp

                print(f"yt-dlp {yt_dlp.version.__version__}")
            else:
                print(f"{package} {importlib.metadata.version(package)}")
        except Exception as exc:
            print(f"{package} missing: {exc.__class__.__name__}")
            return 1
    ffmpeg = shutil.which("ffmpeg")
    print(f"ffmpeg {ffmpeg or 'not found (optional while conversion is disabled)'}")
    print("proxy default: disabled until PROXY_ENABLED=true")
    print("generic extractor default: disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
