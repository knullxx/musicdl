"""
musicdl.resolvers.soundcloud
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Resolver backed by SoundCloud via yt-dlp.

Used as a fallback when the YouTube resolver finds nothing.
SoundCloud is particularly good for:
  - Mixtapes and unofficial releases
  - Explicit tracks that YouTube filters
  - DJ sets and remixes
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from musicdl.core.models import Album, ResolvedSource, Track
from musicdl.resolvers.base import BaseResolver, register_resolver

logger = logging.getLogger(__name__)


@register_resolver
class SoundCloudResolver(BaseResolver):
    """Search SoundCloud for a track via yt-dlp."""

    name = "soundcloud"

    _SEARCH_OPTS = {
        "quiet":         True,
        "no_warnings":   True,
        "skip_download": True,
        "noplaylist":    True,
        "extract_flat":  True,
    }

    _PROFANITY_RE = re.compile(
        r'\b(fuck(ing?)?|shit|bitch(es)?|ass|nigga[s]?|cunt|damn|bastard)\b',
        re.IGNORECASE,
    )

    def resolve(self, track: Track, album: Album) -> Optional[ResolvedSource]:
        """Search SoundCloud for the track."""
        try:
            import yt_dlp
        except ImportError:
            logger.warning("yt-dlp not installed; soundcloud resolver unavailable")
            return None

        base = f"{album.artist.name} {track.title}"
        queries = [f"scsearch1:{base}"]

        # Also try cleaned version if title has words SC might filter
        cleaned = self._PROFANITY_RE.sub("", base).strip()
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        if cleaned != base:
            queries.append(f"scsearch1:{cleaned}")

        for query in queries:
            logger.debug("[soundcloud] Searching: %r", query)
            result = self._try_search(query)
            if result:
                return result

        return None

    def _try_search(self, query: str) -> Optional[ResolvedSource]:
        try:
            import yt_dlp
        except ImportError:
            return None

        try:
            with yt_dlp.YoutubeDL(self._SEARCH_OPTS) as ydl:
                info = ydl.extract_info(query, download=False)
        except Exception as exc:
            logger.debug("[soundcloud] Search error: %s", exc)
            return None

        if not info:
            return None

        if info.get("_type") == "playlist":
            entries = info.get("entries") or []
            if not entries:
                return None
            info = entries[0]
            if not info:
                return None

        webpage_url = info.get("webpage_url") or info.get("url")
        if not webpage_url:
            return None

        if not webpage_url.startswith(("http://", "https://")):
            return None

        # Only accept SoundCloud URLs
        if "soundcloud.com" not in webpage_url:
            logger.debug("[soundcloud] Non-SC URL skipped: %s", webpage_url)
            return None

        duration_s  = info.get("duration")
        duration_ms = int(duration_s * 1000) if duration_s else None

        logger.debug("[soundcloud] Resolved → %s", webpage_url)
        return ResolvedSource(
            url=webpage_url,
            resolver_name=self.name,
            format="mp3",
            quality_kbps=None,
            duration_ms=duration_ms,
            confidence=0.7,  # Slightly lower confidence than YouTube
        )
