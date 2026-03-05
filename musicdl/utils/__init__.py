"""
musicdl.utils
~~~~~~~~~~~~~
Shared utility helpers used throughout the application.
"""

from __future__ import annotations

import logging
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

from musicdl.core.exceptions import PathTraversalError


# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging(level: str = "INFO", log_file: Optional[Path] = None) -> None:
    """Configure root logger. Safe to call multiple times; always takes effect."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    # force=True (Python 3.8+) removes any existing handlers before applying,
    # so this call is idempotent and always wins regardless of prior logging setup.
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers,
        force=True,
    )
    # Silence noisy third-party loggers
    for lib in ("urllib3", "asyncio", "aiohttp", "httpx", "hpack", "musicbrainzngs"):
        logging.getLogger(lib).setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ── Path Safety ───────────────────────────────────────────────────────────────

_DANGEROUS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_STRIP_DOTS      = re.compile(r"^\.+|\.+$")
_WHITESPACE_RUN  = re.compile(r"\s{2,}")
_UNDERSCORE_RUN  = re.compile(r"_+")
_MAX_COMPONENT   = 200   # max chars per path component


def sanitize_filename(name: str) -> str:
    """
    Convert an arbitrary string to a safe filesystem filename component.

    - Strips control characters and characters forbidden on Windows/macOS/Linux
    - Normalises unicode to NFC
    - Collapses whitespace and underscore runs
    - Trims leading/trailing dots and underscores
    - Truncates to _MAX_COMPONENT characters
    - Falls back to 'unknown' if the result is empty or all underscores
    """
    # Unicode normalise
    name = unicodedata.normalize("NFC", name)
    # Replace forbidden characters with underscore
    name = _DANGEROUS_CHARS.sub("_", name)
    # Collapse runs of whitespace
    name = _WHITESPACE_RUN.sub(" ", name).strip()
    # Collapse consecutive underscores to a single one
    name = _UNDERSCORE_RUN.sub("_", name)
    # Strip leading/trailing dots and underscores
    name = _STRIP_DOTS.sub("", name).strip("_ ")
    # Truncate
    name = name[:_MAX_COMPONENT]
    return name or "unknown"


# Windows reserved filenames (case-insensitive)
_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def safe_path(base: Path, *parts: str) -> Path:
    """
    Build a path under *base* from *parts*, each sanitised.

    Raises PathTraversalError if the resolved path escapes *base*.
    This is the single chokepoint for all path construction in the app.
    """
    sanitised = [sanitize_filename(p) for p in parts]

    # Reject Windows reserved names
    for component in sanitised:
        stem = component.split(".")[0].upper()
        if stem in _WINDOWS_RESERVED:
            raise PathTraversalError(component)

    candidate = base.joinpath(*sanitised).resolve()
    resolved_base = base.resolve()

    try:
        candidate.relative_to(resolved_base)
    except ValueError:
        raise PathTraversalError(str(candidate))

    return candidate


# ── URL Validation ────────────────────────────────────────────────────────────

_URL_RE = re.compile(
    r"^https?://"
    r"(?:[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+"
    r")$",
    re.IGNORECASE,
)


def is_valid_url(url: str) -> bool:
    """Return True iff *url* looks like a safe HTTP/HTTPS URL."""
    if not isinstance(url, str):
        return False
    url = url.strip()
    if len(url) > 2048:
        return False
    return bool(_URL_RE.match(url))


# ── Formatting Helpers ────────────────────────────────────────────────────────

def human_bytes(n: int) -> str:
    """Format *n* bytes as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def human_speed(bps: float) -> str:
    """Format bytes-per-second as a human-readable download speed."""
    return f"{human_bytes(int(bps))}/s"


def human_eta(seconds: float) -> str:
    """Format remaining seconds as MM:SS or HH:MM:SS."""
    if seconds < 0 or seconds > 86400 * 10:
        return "?"
    secs = int(seconds)
    if secs >= 3600:
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}"
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"


# ── Misc ──────────────────────────────────────────────────────────────────────

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def track_filename(track_number: int, title: str, ext: str = "mp3") -> str:
    """Generate a zero-padded track filename."""
    safe = sanitize_filename(title)
    ext = ext.lstrip(".")
    return f"{track_number:02d} {safe}.{ext}"
