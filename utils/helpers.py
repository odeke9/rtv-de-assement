from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from config import config


def get_logger(name: str = "rtv") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(message)s")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(config.LOG_DIR / "pipeline.jsonl")):
        h.setFormatter(fmt)
        logger.addHandler(h)
    return logger


def log_event(event: str, **fields) -> None:
    get_logger().info(json.dumps({"ts": round(time.time(), 3), "event": event, **fields}, default=str))


_WS = re.compile(r"\s+")

# trim whitespace & remove extra whitespace in btn headers
def normalize_column(name: str) -> str:
    return _WS.sub(" ", str(name).strip())


# chunks on 1mib
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()
