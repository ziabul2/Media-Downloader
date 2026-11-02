"""Low-cardinality counters. Media URLs and tickets are never labels."""

from __future__ import annotations

import threading


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple, int] = {}

    def inc(self, name: str, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    def render(self) -> str:
        lines = [
            "# HELP zim_requests_total HTTP requests by endpoint and status.",
            "# TYPE zim_requests_total counter",
        ]
        with self._lock:
            items = list(self._counts.items())
        for (name, labels), count in items:
            if labels:
                rendered = ",".join(f'{key}="{value}"' for key, value in labels)
                lines.append(f"{name}{{{rendered}}} {count}")
            else:
                lines.append(f"{name} {count}")
        return "\n".join(lines) + "\n"
