"""
musicdl.metadata.artwork
~~~~~~~~~~~~~~~~~~~~~~~~~
Fetch album cover art from the MusicBrainz Cover Art Archive (CAA).

CAA API: https://musicbrainz.org/doc/Cover_Art_Archive/API
"""

from __future__ import annotations

import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CAA_URL = "https://coverartarchive.org/release-group/{mbid}/front-500"
_TIMEOUT  = 20  # seconds


class ArtworkFetcher:
    """Fetch and save album cover art from the Cover Art Archive."""

    def fetch_url(self, mbid: str) -> Optional[str]:
        """
        Return the direct image URL for the release group *mbid*, or None
        if no artwork is available.

        CAA returns a redirect to the actual image; we follow it and return
        the final URL so callers can cache/re-use it.
        """
        url = _CAA_URL.format(mbid=mbid)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "musicdl/1.0 (https://github.com/musicdl/musicdl)"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                # urlopen follows redirects; resp.url is the final URL
                final_url: str = resp.url
                logger.debug("Artwork URL for %s: %s", mbid, final_url)
                return final_url
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.debug("No artwork available for mbid=%s", mbid)
            else:
                logger.warning("CAA HTTP %d for mbid=%s", exc.code, mbid)
            return None
        except (urllib.error.URLError, OSError) as exc:
            logger.warning("Artwork fetch error for mbid=%s: %s", mbid, exc)
            return None

    def download(self, url: str, dest: Path) -> bool:
        """
        Download the image at *url* to *dest*.
        Returns True on success, False on failure.
        """
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "musicdl/1.0 (https://github.com/musicdl/musicdl)"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                dest.write_bytes(resp.read())
            logger.info("Artwork saved: %s", dest.name)
            return True
        except (urllib.error.URLError, OSError) as exc:
            logger.warning("Artwork download failed (%s): %s", url, exc)
            return False
