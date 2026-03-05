"""
musicdl.resolvers.spotify
~~~~~~~~~~~~~~~~~~~~~~~~~~
Spotify link parser. Extracts track/album/playlist info from Spotify
using the public oEmbed API (no auth required) and yt-dlp metadata,
then maps it to MusicBrainz for proper metadata.

Supported URL formats:
  https://open.spotify.com/track/xxx
  https://open.spotify.com/album/xxx
  https://open.spotify.com/playlist/xxx
"""

from __future__ import annotations

import logging
import re
import urllib.request
import json
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_SPOTIFY_RE = re.compile(
    r"https?://open\.spotify\.com/(track|album|playlist|artist)/([A-Za-z0-9]+)"
)


def parse_spotify_url(url: str) -> Optional[Tuple[str, str]]:
    """
    Parse a Spotify URL and return (type, id) or None if not a Spotify URL.
    type is one of: track, album, playlist, artist
    """
    m = _SPOTIFY_RE.match(url.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def is_spotify_url(url: str) -> bool:
    return bool(_SPOTIFY_RE.match(url.strip()))


def extract_spotify_tracks(url: str) -> List[dict]:
    """
    Extract track info from a Spotify URL using yt-dlp.
    Returns a list of dicts with keys: title, artist, album
    
    yt-dlp supports Spotify and can extract track metadata without
    needing a Spotify API key.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp not installed")
        return []

    ydl_opts = {
        "quiet":         True,
        "no_warnings":   True,
        "skip_download": True,
        "extract_flat":  True,
    }

    tracks = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return []

        # Single track
        if info.get("_type") != "playlist":
            tracks.append(_extract_track_info(info))
            return tracks

        # Album or playlist — entries is the track list
        for entry in info.get("entries") or []:
            if entry:
                tracks.append(_extract_track_info(entry))

    except Exception as exc:
        logger.warning("Spotify extraction failed: %s", exc)

    return [t for t in tracks if t]


def _extract_track_info(info: dict) -> Optional[dict]:
    title  = info.get("track") or info.get("title") or ""
    artist = info.get("artist") or info.get("uploader") or ""
    album  = info.get("album") or ""
    if not title:
        return None
    return {"title": title, "artist": artist, "album": album}
