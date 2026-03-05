"""
musicdl.resolvers
~~~~~~~~~~~~~~~~~
Exports resolve_track() and auto-imports all built-in resolver modules
so their @register_resolver decorators fire.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from musicdl.core.models import Album, ResolvedSource, Track
from musicdl.resolvers.base import BaseResolver, build_resolver_chain

# Auto-import built-in resolvers so they self-register
from musicdl.resolvers import ytdlp       # noqa: F401
from musicdl.resolvers import soundcloud  # noqa: F401

logger = logging.getLogger(__name__)


def resolve_track(
    track: Track,
    album: Album,
    resolvers: List[BaseResolver],
) -> Optional[ResolvedSource]:
    """
    Try each resolver in order and return the first successful result.
    Returns None if all resolvers fail.
    """
    for resolver in resolvers:
        try:
            source = resolver.resolve(track, album)
            if source:
                logger.debug(
                    "Resolved %r via %s (confidence=%.2f)",
                    track.title, resolver.name, source.confidence,
                )
                return source
        except Exception as exc:
            logger.warning(
                "Resolver %r raised an error for %r: %s",
                resolver.name, track.title, exc,
            )
    return None


__all__ = ["resolve_track", "build_resolver_chain"]
