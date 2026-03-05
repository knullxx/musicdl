"""
musicdl.library.database
~~~~~~~~~~~~~~~~~~~~~~~~~
SQLite-backed storage for the local music library.

Schema:
  artists  (id, mbid, name, country)
  albums   (id, mbid, title, artist_id, year, release_type, label, format)
  tracks   (id, mbid, title, album_id, track_number, disc_number, duration_ms, file_path, downloaded_at)
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mbid        TEXT UNIQUE,
    name        TEXT NOT NULL,
    country     TEXT
);

CREATE TABLE IF NOT EXISTS albums (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mbid         TEXT UNIQUE,
    title        TEXT NOT NULL,
    artist_id    INTEGER REFERENCES artists(id),
    year         INTEGER,
    release_type TEXT,
    label        TEXT,
    format       TEXT DEFAULT 'mp3'
);

CREATE TABLE IF NOT EXISTS tracks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    mbid          TEXT,
    title         TEXT NOT NULL,
    album_id      INTEGER REFERENCES albums(id),
    track_number  INTEGER,
    disc_number   INTEGER DEFAULT 1,
    duration_ms   INTEGER,
    file_path     TEXT UNIQUE,
    downloaded_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tracks_album  ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id);
CREATE INDEX IF NOT EXISTS idx_artists_name  ON artists(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_albums_title  ON albums(title COLLATE NOCASE);
"""


class LibraryDB:
    """Thin SQLite wrapper for the local music library."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.debug("Library DB open: %s", db_path)

    def close(self) -> None:
        self._conn.close()

    # ── Write ──────────────────────────────────────────────────────────────

    def upsert_artist(self, mbid: str, name: str, country: Optional[str] = None) -> int:
        self._conn.execute(
            "INSERT INTO artists (mbid, name, country) VALUES (?,?,?) "
            "ON CONFLICT(mbid) DO UPDATE SET name=excluded.name, country=excluded.country",
            (mbid, name, country),
        )
        self._conn.commit()
        cur = self._conn.execute("SELECT id FROM artists WHERE mbid=?", (mbid,))
        return cur.fetchone()["id"]

    def upsert_album(
        self,
        mbid: str,
        title: str,
        artist_id: int,
        year: Optional[int],
        release_type: str,
        label: Optional[str],
        fmt: str,
    ) -> int:
        self._conn.execute(
            "INSERT INTO albums (mbid, title, artist_id, year, release_type, label, format) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(mbid) DO UPDATE SET title=excluded.title, format=excluded.format",
            (mbid, title, artist_id, year, release_type, label, fmt),
        )
        self._conn.commit()
        cur = self._conn.execute("SELECT id FROM albums WHERE mbid=?", (mbid,))
        return cur.fetchone()["id"]

    def upsert_track(
        self,
        title: str,
        album_id: int,
        track_number: int,
        disc_number: int,
        file_path: str,
        duration_ms: Optional[int] = None,
        mbid: Optional[str] = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO tracks (mbid, title, album_id, track_number, disc_number, "
            "duration_ms, file_path, downloaded_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(file_path) DO UPDATE SET downloaded_at=excluded.downloaded_at",
            (mbid, title, album_id, track_number, disc_number, duration_ms, file_path, now),
        )
        self._conn.commit()
        cur = self._conn.execute("SELECT id FROM tracks WHERE file_path=?", (file_path,))
        return cur.fetchone()["id"]

    # ── Read ───────────────────────────────────────────────────────────────

    def search_artists(self, query: str) -> List[Dict]:
        cur = self._conn.execute(
            "SELECT * FROM artists WHERE name LIKE ? ORDER BY name",
            (f"%{query}%",),
        )
        return [dict(r) for r in cur.fetchall()]

    def search_albums(self, query: str) -> List[Dict]:
        cur = self._conn.execute(
            """SELECT al.*, ar.name as artist_name
               FROM albums al JOIN artists ar ON al.artist_id = ar.id
               WHERE al.title LIKE ? OR ar.name LIKE ?
               ORDER BY ar.name, al.year""",
            (f"%{query}%", f"%{query}%"),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_all_albums(self) -> List[Dict]:
        cur = self._conn.execute(
            """SELECT al.*, ar.name as artist_name,
               COUNT(t.id) as track_count
               FROM albums al
               JOIN artists ar ON al.artist_id = ar.id
               LEFT JOIN tracks t ON t.album_id = al.id
               GROUP BY al.id
               ORDER BY ar.name, al.year"""
        )
        return [dict(r) for r in cur.fetchall()]

    def get_tracks_for_album(self, album_id: int) -> List[Dict]:
        cur = self._conn.execute(
            "SELECT * FROM tracks WHERE album_id=? ORDER BY disc_number, track_number",
            (album_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def stats(self) -> Dict:
        artists = self._conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
        albums  = self._conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
        tracks  = self._conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        dur     = self._conn.execute(
            "SELECT SUM(duration_ms) FROM tracks WHERE duration_ms IS NOT NULL"
        ).fetchone()[0] or 0
        return {
            "artists": artists,
            "albums":  albums,
            "tracks":  tracks,
            "total_duration_ms": dur,
        }

    def find_duplicates(self) -> List[Dict]:
        """Find tracks with the same title + album that appear more than once."""
        cur = self._conn.execute(
            """SELECT title, album_id, COUNT(*) as count, GROUP_CONCAT(file_path, '|') as paths
               FROM tracks
               GROUP BY title, album_id
               HAVING count > 1"""
        )
        return [dict(r) for r in cur.fetchall()]

    def track_exists(self, file_path: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM tracks WHERE file_path=?", (file_path,)
        )
        return cur.fetchone() is not None
