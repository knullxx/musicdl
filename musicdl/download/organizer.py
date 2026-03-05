"""
musicdl.download.organizer
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Responsible for:
  - Building the folder structure: Music/Artist/Album (Year)/
  - Generating DownloadTask objects for each track
  - Checking for existing files (skip-existing)
  - Downloading and placing album artwork
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from musicdl.core.models import Album, Artist, DownloadStatus, DownloadTask, Track
from musicdl.utils import safe_path, sanitize_filename, track_filename

logger = logging.getLogger(__name__)


class FileOrganizer:
    """
    Translates Album/Track metadata into filesystem paths and
    creates DownloadTask objects ready for the downloader.
    """

    def __init__(
        self,
        output_dir: Path,
        audio_format: str = "mp3",
        skip_existing: bool = True,
    ) -> None:
        self._output_dir   = output_dir.resolve()
        self._audio_format = audio_format.lstrip(".")
        self._skip_existing = skip_existing

    # ── Path construction ─────────────────────────────────────────────────

    def artist_dir(self, artist: Artist) -> Path:
        """Return the artist-level directory path (does not create it)."""
        return safe_path(self._output_dir, sanitize_filename(artist.name))

    def album_dir(self, album: Album) -> Path:
        """Return the album-level directory path (does not create it)."""
        return safe_path(
            self.artist_dir(album.artist),
            album.folder_name(),
        )

    def ensure_album_dir(self, album: Album) -> Path:
        """Return the album directory, creating it and parents if needed."""
        path = self.album_dir(album)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def track_path(self, track: Track, album: Album) -> Path:
        """Return the full destination path for a track file (no mkdir)."""
        filename = track_filename(track.track_number, track.title, self._audio_format)
        return safe_path(self.album_dir(album), filename)

    def artwork_path(self, album: Album) -> Path:
        """Return the path where album artwork should be stored (no mkdir)."""
        return safe_path(self.album_dir(album), "cover.jpg")

    # ── Task creation ──────────────────────────────────────────────────────

    def build_tasks(self, album: Album) -> List[DownloadTask]:
        """
        Create one DownloadTask per track in *album*.
        Tasks for already-existing files are marked SKIPPED immediately.
        """
        tasks: List[DownloadTask] = []

        for track in album.tracks:
            output_path = self.track_path(track, album)
            task = DownloadTask(
                track=track,
                album=album,
                output_path=output_path,
            )

            if self._skip_existing and output_path.exists():
                task.status = DownloadStatus.SKIPPED
                logger.debug("Skipping existing: %s", output_path.name)

            tasks.append(task)

        return tasks

    def build_tasks_for_albums(self, albums: List[Album]) -> List[DownloadTask]:
        """Build tasks for an entire list of albums."""
        all_tasks: List[DownloadTask] = []
        for album in albums:
            all_tasks.extend(self.build_tasks(album))
        return all_tasks

    # ── Statistics helpers ────────────────────────────────────────────────

    @staticmethod
    def count_pending(tasks: List[DownloadTask]) -> int:
        return sum(1 for t in tasks if t.status == DownloadStatus.PENDING)

    @staticmethod
    def count_skipped(tasks: List[DownloadTask]) -> int:
        return sum(1 for t in tasks if t.status == DownloadStatus.SKIPPED)

    @staticmethod
    def count_completed(tasks: List[DownloadTask]) -> int:
        return sum(1 for t in tasks if t.status == DownloadStatus.COMPLETED)

    @staticmethod
    def count_failed(tasks: List[DownloadTask]) -> int:
        return sum(1 for t in tasks if t.status == DownloadStatus.FAILED)
