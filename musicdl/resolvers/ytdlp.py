"""
musicdl.resolvers.ytdlp
~~~~~~~~~~~~~~~~~~~~~~~
Resolver backed by yt-dlp.

yt-dlp supports 1000+ sites including YouTube, SoundCloud, and Bandcamp.

DESIGN NOTE: This resolver returns the *webpage URL* (e.g. a YouTube watch
URL), not a raw stream URL. Raw stream URLs from yt-dlp expire quickly
(typically within minutes) and are useless by the time the downloader
actually fetches them. Returning the webpage URL lets the downloader
re-invoke yt-dlp at download time with full retry and post-processing.

The resolver's job here is just to confirm a match exists and return
a stable URL that the downloader can act on.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from musicdl.core.models import Album, ResolvedSource, Track
from musicdl.resolvers.base import BaseResolver, register_resolver

logger = logging.getLogger(__name__)


@register_resolver
class YtDlpResolver(BaseResolver):
    """Search YouTube (and other yt-dlp supported sites) for a track."""

    name = "ytdlp"

    # Options for metadata-only extraction — no download, no stream URL
    _SEARCH_OPTS = {
        "quiet":         True,
        "no_warnings":   True,
        "skip_download": True,
        "noplaylist":    True,
        # extract_flat=True gives us the webpage_url without resolving streams
        "extract_flat":  True,
    }

    # Words YouTube safe search may filter — strip from search query only (not filename)
    _PROFANITY_RE = re.compile(
        r'\b(fuck(ing?)?|shit|bitch(es)?|ass|nigga[s]?|cunt|damn|bastard)\b',
        re.IGNORECASE,
    )

    def resolve(self, track: Track, album: Album) -> Optional[ResolvedSource]:
        """
        Search YouTube for the best match and return its stable webpage URL.
        Falls back to a sanitized query if the first search returns nothing.
        """
        try:
            import yt_dlp
        except ImportError:
            logger.warning("yt-dlp not installed; ytdlp resolver unavailable")
            return None

        base_query = f"{album.artist.name} {track.title} {album.title}"
        queries = [f"ytsearch1:{base_query}"]

        # If title contains words YouTube might filter, also try a cleaned version
        cleaned = self._PROFANITY_RE.sub("", base_query).strip()
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        if cleaned != base_query:
            queries.append(f"ytsearch1:{cleaned}")
            # Also try just artist + cleaned title
            clean_title = self._PROFANITY_RE.sub("", track.title).strip()
            queries.append(f"ytsearch1:{album.artist.name} {clean_title}")

        for query in queries:
            logger.debug("[ytdlp] Searching: %r", query)
            result = self._try_search(query)
            if result:
                return result

        return None

    def _try_search(self, query: str) -> Optional["ResolvedSource"]:
        """Run a single yt-dlp search query and return a ResolvedSource or None."""
        try:
            import yt_dlp
        except ImportError:
            return None

        try:
            with yt_dlp.YoutubeDL(self._SEARCH_OPTS) as ydl:
                info = ydl.extract_info(query, download=False)
        except Exception as exc:
            logger.debug("[ytdlp] Search error: %s", exc)
            return None

        if not info:
            return None

        # ytsearch returns a playlist wrapper; unwrap the first entry
        if info.get("_type") == "playlist":
            entries = info.get("entries") or []
            if not entries:
                return None
            info = entries[0]
            if not info:
                return None

        # Prefer webpage_url (stable) over url (may be a raw stream)
        webpage_url = info.get("webpage_url") or info.get("url")
        if not webpage_url:
            return None

        # Sanity check: must look like a real URL
        if not webpage_url.startswith(("http://", "https://")):
            logger.debug("[ytdlp] Skipping non-HTTP URL: %r", webpage_url)
            return None

        duration_s = info.get("duration")
        duration_ms = int(duration_s * 1000) if duration_s else None

        logger.debug("[ytdlp] Resolved → %s", webpage_url)
        return ResolvedSource(
            url=webpage_url,
            resolver_name=self.name,
            format="mp3",            # yt-dlp will transcode to preferred format
            quality_kbps=None,       # determined at download time
            duration_ms=duration_ms,
            confidence=0.8,
        )
