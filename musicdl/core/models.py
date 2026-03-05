"""
musicdl.core.models
~~~~~~~~~~~~~~~~~~~~
Dataclasses and enums that represent the domain objects used throughout musicdl.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple


# ── Enums ──────────────────────────────────────────────────────────────────────

class ReleaseType(str, Enum):
    ALBUM       = "album"
    EP          = "ep"
    SINGLE      = "single"
    COMPILATION = "compilation"
    LIVE        = "live"
    OTHER       = "other"

    @classmethod
    def from_mb(cls, value: str) -> "ReleaseType":
        """Map a MusicBrainz primary-type string to a ReleaseType."""
        mapping = {
            "album":       cls.ALBUM,
            "ep":          cls.EP,
            "single":      cls.SINGLE,
            "compilation": cls.COMPILATION,
            "live":        cls.LIVE,
            "broadcast":   cls.OTHER,
            "other":       cls.OTHER,
        }
        return mapping.get(value.lower(), cls.OTHER)


class DownloadStatus(str, Enum):
    PENDING   = "pending"
    SKIPPED   = "skipped"
    COMPLETED = "completed"
    FAILED    = "failed"


# ── Domain models ──────────────────────────────────────────────────────────────

@dataclass
class Artist:
    mbid:           str
    name:           str
    sort_name:      str = ""
    country:        Optional[str] = None
    disambiguation: Optional[str] = None

    def __str__(self) -> str:
        return self.name


@dataclass
class Track:
    title:        str
    track_number: int = 0
    disc_number:  int = 1
    duration_ms:  Optional[int] = None
    mbid:         Optional[str] = None
    isrc:         Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        return self.duration_ms / 1000 if self.duration_ms else None

    def __str__(self) -> str:
        return f"{self.track_number:02d}. {self.title}"


@dataclass
class Album:
    title:        str
    artist:       Artist
    tracks:       Tuple[Track, ...] = field(default_factory=tuple)
    year:         Optional[int] = None
    release_type: ReleaseType = ReleaseType.ALBUM
    mbid:         Optional[str] = None
    genres:       Tuple[str, ...] = field(default_factory=tuple)
    label:        Optional[str] = None
    country:      Optional[str] = None

    @property
    def total_discs(self) -> int:
        if not self.tracks:
            return 1
        return max(t.disc_number for t in self.tracks)

    def folder_name(self) -> str:
        """Human-readable folder name: 'Title (Year)' or just 'Title'."""
        if self.year:
            return f"{self.title} ({self.year})"
        return self.title

    def __str__(self) -> str:
        year = str(self.year) if self.year else "????"
        return f"{self.artist.name} – {self.title} [{year}]"


@dataclass
class ResolvedSource:
    """A concrete URL that can be downloaded for a track."""
    url:           str
    resolver_name: str
    format:        str = "mp3"
    quality_kbps:  Optional[int] = None
    duration_ms:   Optional[int] = None
    confidence:    float = 1.0


@dataclass
class DownloadTask:
    """Everything needed to download a single track."""
    track:        Track
    album:        Album
    output_path:  Path
    status:       DownloadStatus = DownloadStatus.PENDING
    resolved_url: Optional[str] = None
    error:        Optional[str] = None
    bytes_total:  int = 0
    bytes_done:   int = 0

    @property
    def progress(self) -> float:
        """Download progress as a 0.0–1.0 fraction."""
        if self.bytes_total <= 0:
            return 0.0
        return min(self.bytes_done / self.bytes_total, 1.0)
