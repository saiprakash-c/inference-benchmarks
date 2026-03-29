"""
Structured JSON logger for all benchmark targets.

No print() calls anywhere — use log() from this module.
Output format: {"level": "...", "event": "...", "ts": "...", "data": {...}}
"""

import json
import sys
from datetime import datetime, timezone


def log(level: str, event: str, **data: object) -> None:
    record: dict[str, object] = {
        "level": level,
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if data:
        record["data"] = data
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()


def info(event: str, **data: object) -> None:
    log("INFO", event, **data)


def warn(event: str, **data: object) -> None:
    log("WARN", event, **data)


def error(event: str, **data: object) -> None:
    log("ERROR", event, **data)
