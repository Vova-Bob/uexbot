"""
Tiny disk cache helper (JSON + TTL) for simple API responses.

- Stored under <project_root>/data/cache/{name}.json
- API: load_json_cache(name, max_age_sec) -> data | None
       save_json_cache(name, data) -> None
"""

from __future__ import annotations
import json
import os
import time
from typing import Any, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

def _path(name: str) -> str:
    return os.path.join(_CACHE_DIR, f"{name}.json")

def load_json_cache(name: str, max_age_sec: int) -> Optional[Any]:
    """Load cached value if file exists and is fresh; else None."""
    p = _path(name)
    if not os.path.exists(p):
        return None
    try:
        stat = os.stat(p)
        if time.time() - stat.st_mtime > max_age_sec:
            return None
        with open(p, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("data", payload)
    except Exception:
        return None

def save_json_cache(name: str, data: Any) -> None:
    """Write data atomically to cache file."""
    p = _path(name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"data": data}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
