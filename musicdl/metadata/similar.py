"""
musicdl.metadata.similar
~~~~~~~~~~~~~~~~~~~~~~~~~
Suggest similar artists using MusicBrainz artist relations.
"""

from __future__ import annotations

import logging
from typing import List, Optional

try:
    import musicbrainzngs as mb
    _MB_AVAILABLE = True
except ImportError:
    _MB_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_similar_artists(artist_mbid: str, limit: int = 10) -> List[dict]:
    """
    Fetch artists related to *artist_mbid* via MusicBrainz artist-rels.
    Returns a list of dicts with keys: name, mbid, relation_type
    """
    if not _MB_AVAILABLE:
        logger.warning("musicbrainzngs not installed")
        return []
    try:
        result = mb.get_artist_by_id(artist_mbid, includes=["artist-rels"])
    except Exception as exc:
        logger.warning("Could not fetch artist relations: %s", exc)
        return []

    artist_data = result.get("artist", {})
    relations   = artist_data.get("artist-relation-list", [])

    similar = []
    seen    = set()

    for rel in relations:
        related = rel.get("artist", {})
        name    = related.get("name")
        mbid    = related.get("id")
        rtype   = rel.get("type", "related")

        if not name or not mbid or mbid in seen:
            continue
        seen.add(mbid)
        similar.append({"name": name, "mbid": mbid, "relation": rtype})

        if len(similar) >= limit:
            break

    return similar
