"""
musicdl.metadata.tagger
~~~~~~~~~~~~~~~~~~~~~~~~
Embed ID3 / MP4 / FLAC / Ogg metadata tags into audio files.

Supported formats:
  .mp3   → ID3v2.4 tags      (mutagen.id3)
  .m4a   → iTunes MP4 atoms  (mutagen.mp4)
  .flac  → Vorbis comments   (mutagen.flac)
  .ogg   → Vorbis comments   (mutagen.oggvorbis)
  .opus  → Opus comments     (mutagen.oggopus)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from musicdl.core.models import Album, Track

logger = logging.getLogger(__name__)


def tag_file(
    path: Path,
    track: Track,
    album: Album,
    artwork_path: Optional[Path] = None,
) -> bool:
    """
    Embed metadata into the audio file at *path*.

    Returns True on success, False if the format is unsupported or tagging
    fails non-fatally.  Never raises; all exceptions are caught and logged.
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".mp3":
            return _tag_mp3(path, track, album, artwork_path)
        elif suffix in (".m4a", ".mp4", ".aac"):
            return _tag_mp4(path, track, album, artwork_path)
        elif suffix == ".flac":
            return _tag_flac(path, track, album, artwork_path)
        elif suffix == ".ogg":
            return _tag_ogg(path, track, album)
        elif suffix == ".opus":
            return _tag_opus(path, track, album)
        else:
            logger.warning("No tagger for format %r (%s)", suffix, path.name)
            return False
    except Exception as exc:
        logger.error("Tagging failed for %s: %s", path.name, exc)
        return False


# ── MP3 ───────────────────────────────────────────────────────────────────────

def _tag_mp3(
    path: Path,
    track: Track,
    album: Album,
    artwork_path: Optional[Path],
) -> bool:
    try:
        from mutagen.id3 import (
            APIC, ID3, ID3NoHeaderError, TALB, TDRC, TCON, TIT2, TPOS, TPE1, TRCK,
        )
        from mutagen._util import MutagenError
    except ImportError:
        logger.warning("mutagen not installed; skipping ID3 tagging")
        return False

    try:
        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()

        # Remove any existing artwork to avoid duplicate APIC frames
        tags.delall("APIC")

        tags["TIT2"] = TIT2(encoding=3, text=track.title)
        tags["TPE1"] = TPE1(encoding=3, text=album.artist.name)
        tags["TALB"] = TALB(encoding=3, text=album.title)
        tags["TRCK"] = TRCK(encoding=3, text=f"{track.track_number}/{len(album.tracks)}")
        tags["TPOS"] = TPOS(encoding=3, text=f"{track.disc_number}/{album.total_discs}")

        if album.year:
            tags["TDRC"] = TDRC(encoding=3, text=str(album.year))
        if album.genres:
            tags["TCON"] = TCON(encoding=3, text="; ".join(album.genres))

        if artwork_path and artwork_path.exists():
            tags["APIC"] = APIC(
                encoding=3,
                mime=_mime_for_image(artwork_path),
                type=3,           # 3 = Cover (front)
                desc="Cover",
                data=artwork_path.read_bytes(),
            )

        tags.save(str(path), v2_version=4)
        return True

    except MutagenError as exc:
        logger.warning("MP3 tagging error on %s: %s", path.name, exc)
        return False


# ── M4A / AAC ─────────────────────────────────────────────────────────────────

def _tag_mp4(
    path: Path,
    track: Track,
    album: Album,
    artwork_path: Optional[Path],
) -> bool:
    try:
        from mutagen.mp4 import MP4, MP4Cover
        from mutagen._util import MutagenError  # FIX: correct import path
    except ImportError:
        logger.warning("mutagen not installed; skipping MP4 tagging")
        return False

    try:
        tags = MP4(str(path))
        tags["\xa9nam"] = [track.title]
        tags["\xa9ART"] = [album.artist.name]
        tags["\xa9alb"] = [album.title]
        tags["trkn"]    = [(track.track_number, len(album.tracks))]
        tags["disk"]    = [(track.disc_number, album.total_discs)]

        if album.year:
            tags["\xa9day"] = [str(album.year)]
        if album.genres:
            tags["\xa9gen"] = ["; ".join(album.genres)]

        if artwork_path and artwork_path.exists():
            img_fmt = (
                MP4Cover.FORMAT_PNG
                if artwork_path.suffix.lower() == ".png"
                else MP4Cover.FORMAT_JPEG
            )
            tags["covr"] = [MP4Cover(artwork_path.read_bytes(), imageformat=img_fmt)]

        tags.save()
        return True

    except MutagenError as exc:
        logger.warning("MP4 tagging error on %s: %s", path.name, exc)
        return False


# ── FLAC ──────────────────────────────────────────────────────────────────────

def _tag_flac(
    path: Path,
    track: Track,
    album: Album,
    artwork_path: Optional[Path],
) -> bool:
    try:
        from mutagen.flac import FLAC, Picture
        from mutagen._util import MutagenError
    except ImportError:
        logger.warning("mutagen not installed; skipping FLAC tagging")
        return False

    try:
        tags = FLAC(str(path))
        tags["title"]        = [track.title]
        tags["artist"]       = [album.artist.name]
        tags["album"]        = [album.title]
        tags["tracknumber"]  = [str(track.track_number)]
        tags["totaltracks"]  = [str(len(album.tracks))]
        tags["discnumber"]   = [str(track.disc_number)]
        tags["totaldiscs"]   = [str(album.total_discs)]

        if album.year:
            tags["date"] = [str(album.year)]
        if album.genres:
            tags["genre"] = list(album.genres)
        if album.label:
            tags["organization"] = [album.label]

        if artwork_path and artwork_path.exists():
            pic = Picture()
            pic.type = 3              # Front cover
            pic.mime = _mime_for_image(artwork_path)
            pic.desc = "Cover"
            pic.data = artwork_path.read_bytes()
            tags.clear_pictures()
            tags.add_picture(pic)

        tags.save()
        return True

    except MutagenError as exc:
        logger.warning("FLAC tagging error on %s: %s", path.name, exc)
        return False


# ── OGG Vorbis ────────────────────────────────────────────────────────────────

def _tag_ogg(path: Path, track: Track, album: Album) -> bool:
    try:
        from mutagen.oggvorbis import OggVorbis
        from mutagen._util import MutagenError
    except ImportError:
        logger.warning("mutagen not installed; skipping OGG tagging")
        return False

    try:
        tags = OggVorbis(str(path))
        tags["title"]       = [track.title]
        tags["artist"]      = [album.artist.name]
        tags["album"]       = [album.title]
        tags["tracknumber"] = [str(track.track_number)]
        if album.year:
            tags["date"] = [str(album.year)]
        if album.genres:
            tags["genre"] = list(album.genres)
        tags.save()
        return True
    except MutagenError as exc:
        logger.warning("OGG tagging error on %s: %s", path.name, exc)
        return False


# ── Opus ──────────────────────────────────────────────────────────────────────

def _tag_opus(path: Path, track: Track, album: Album) -> bool:
    try:
        from mutagen.oggopus import OggOpus
        from mutagen._util import MutagenError
    except ImportError:
        logger.warning("mutagen not installed; skipping Opus tagging")
        return False

    try:
        tags = OggOpus(str(path))
        tags["title"]       = [track.title]
        tags["artist"]      = [album.artist.name]
        tags["album"]       = [album.title]
        tags["tracknumber"] = [str(track.track_number)]
        if album.year:
            tags["date"] = [str(album.year)]
        if album.genres:
            tags["genre"] = list(album.genres)
        tags.save()
        return True
    except MutagenError as exc:
        logger.warning("Opus tagging error on %s: %s", path.name, exc)
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mime_for_image(path: Path) -> str:
    """Return MIME type for a cover image path."""
    return {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".webp": "image/webp",
        ".gif":  "image/gif",
    }.get(path.suffix.lower(), "image/jpeg")
