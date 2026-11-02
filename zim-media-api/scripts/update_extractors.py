"""Show the pinned yt-dlp version. Bump requirements.txt deliberately; do not float it."""

from __future__ import annotations

import importlib.metadata


def main() -> None:
    print(importlib.metadata.version("yt-dlp"))
    print("Update by changing the yt-dlp pin in requirements.txt, reinstalling, and rerunning tests.")
    print("Do not enable geo_bypass or cookie login while updating.")


if __name__ == "__main__":
    main()
