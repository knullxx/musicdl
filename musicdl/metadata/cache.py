"""
musicdl.metadata.cache
~~~~~~~~~~~~~~~~~~~~~~~
Simple disk-backed JSON cache with TTL expiry.

Cache files are stored as:
    <cache_dir>/<sha256_of_key>.json

Each file contains:
    { "expires": <unix timestamp>, "value": <any JSON-serialisable value> }
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from musicdl.core.exceptions import CacheError

logger = logging.getLogger(__name__)


class MetadataCache:
    """Persistent JSON cache with TTL-based expiry."""

    def __init__(self, cache_dir: Path, ttl_hours: int = 72) -> None:
        self._dir = cache_dir
        self._ttl = ttl_hours * 3600
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CacheError(f"Cannot create cache directory {cache_dir}: {exc}") from exc

    # ── Public API ────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """Return cached value for *key*, or None if missing/expired."""
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Cache read error for %r: %s", key, exc)
            return None

        if time.time() > data.get("expires", 0):
            logger.debug("Cache expired for %r", key)
            path.unlink(missing_ok=True)
            return None

        logger.debug("Cache hit: %r", key)
        return data.get("value")

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key* with the configured TTL."""
        path = self._path_for(key)
        payload = {
            "expires": time.time() + self._ttl,
            "value":   value,
        }
        try:
            path.write_text(json.dumps(payload), encoding="utf-8")
            logger.debug("Cache set: %r", key)
        except (OSError, TypeError) as exc:
            logger.warning("Cache write error for %r: %s", key, exc)

    def delete(self, key: str) -> None:
        """Remove a single cache entry."""
        self._path_for(key).unlink(missing_ok=True)

    def clear(self) -> int:
        """Delete all cache files. Returns the number of files removed."""
        removed = 0
        for f in self._dir.glob("*.json"):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
        logger.info("Cache cleared (%d files removed)", removed)
        return removed

    def purge_expired(self) -> int:
        """Delete only expired entries. Returns number removed."""
        removed = 0
        now = time.time()
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if now > data.get("expires", 0):
                    f.unlink()
                    removed += 1
            except (json.JSONDecodeError, OSError):
                f.unlink(missing_ok=True)
                removed += 1
        logger.info("Purged %d expired cache entries", removed)
        return removed

    # ── Internal ──────────────────────────────────────────────────────────

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self._dir / f"{digest}.json"
