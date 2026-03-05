"""
musicdl.library.manager
~~~~~~~~~~~~~~~~~~~~~~~~
High-level library operations: register downloads, list, search, scan, dedup.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from musicdl.core.models import Album, DownloadStatus, DownloadTask
from musicdl.library.database import LibraryDB

logger = logging.getLogger(__name__)


class LibraryManager:
    """Manages the local music library database."""

    def __init__(self, db_path: Path) -> None:
        self._db = LibraryDB(db_path)

    def close(self) -> None:
        self._db.close()

    # ── Register downloads ─────────────────────────────────────────────────

    def register_completed_tasks(self, tasks: List[DownloadTask]) -> int:
        """
        After a pipeline run, register all completed tasks in the library.
        Returns the number of tracks registered.
        """
        registered = 0
        for task in tasks:
            if task.status != DownloadStatus.COMPLETED:
                continue
            if not task.output_path.exists():
                continue
            try:
                self._register_track(task)
                registered += 1
            except Exception as exc:
                logger.warning("Failed to register %s: %s", task.track.title, exc)
        return registered

    def _register_track(self, task: DownloadTask) -> None:
        album  = task.album
        artist = album.artist

        artist_id = self._db.upsert_artist(
            mbid=artist.mbid,
            name=artist.name,
            country=artist.country,
        )
        album_id = self._db.upsert_album(
            mbid=album.mbid or f"local:{album.title}",
            title=album.title,
            artist_id=artist_id,
            year=album.year,
            release_type=album.release_type.value,
            label=album.label,
            fmt=task.output_path.suffix.lstrip("."),
        )
        self._db.upsert_track(
            title=task.track.title,
            album_id=album_id,
            track_number=task.track.track_number,
            disc_number=task.track.disc_number,
            file_path=str(task.output_path),
            duration_ms=task.track.duration_ms,
            mbid=task.track.mbid,
        )

    # ── Query ──────────────────────────────────────────────────────────────

    def list_albums(self, query: Optional[str] = None) -> List[Dict]:
        if query:
            return self._db.search_albums(query)
        return self._db.get_all_albums()

    def list_artists(self, query: Optional[str] = None) -> List[Dict]:
        if query:
            return self._db.search_artists(query)
        cur = self._db._conn.execute("SELECT * FROM artists ORDER BY name")
        return [dict(r) for r in cur.fetchall()]

    def stats(self) -> Dict:
        return self._db.stats()

    def find_duplicates(self) -> List[Dict]:
        return self._db.find_duplicates()

    def scan_directory(self, music_dir: Path, audio_extensions=(".mp3", ".m4a", ".flac", ".ogg", ".opus")) -> int:
        """
        Scan a directory for audio files and register any that aren't in the library yet.
        Useful for importing existing music collections.
        Returns the number of new files found.
        """
        found = 0
        for ext in audio_extensions:
            for f in music_dir.rglob(f"*{ext}"):
                if self._db.track_exists(str(f)):
                    continue
                # Try to extract info from path: Music/Artist/Album (Year)/Track.mp3
                try:
                    parts = f.parts
                    title = f.stem
                    # Strip leading track number if present (e.g. "01 Title" → "Title")
                    if len(title) > 3 and title[:2].isdigit() and title[2] == " ":
                        title = title[3:]

                    # Try to find artist/album from folder structure
                    artist_name = parts[-3] if len(parts) >= 3 else "Unknown Artist"
                    album_folder = parts[-2] if len(parts) >= 2 else "Unknown Album"
                    album_title = album_folder
                    year = None
                    if album_folder.endswith(")") and "(" in album_folder:
                        year_str = album_folder.rsplit("(", 1)[-1].rstrip(")")
                        try:
                            year = int(year_str)
                            album_title = album_folder.rsplit("(", 1)[0].strip()
                        except ValueError:
                            pass

                    artist_id = self._db.upsert_artist(
                        mbid=f"local:{artist_name}",
                        name=artist_name,
                    )
                    album_id = self._db.upsert_album(
                        mbid=f"local:{artist_name}:{album_title}",
                        title=album_title,
                        artist_id=artist_id,
                        year=year,
                        release_type="album",
                        label=None,
                        fmt=ext.lstrip("."),
                    )
                    self._db.upsert_track(
                        title=title,
                        album_id=album_id,
                        track_number=0,
                        disc_number=1,
                        file_path=str(f),
                    )
                    found += 1
                except Exception as exc:
                    logger.debug("Could not import %s: %s", f, exc)
        logger.info("Scanned %d new files from %s", found, music_dir)
        return found
