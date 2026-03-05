"""
musicdl.resolvers.base
~~~~~~~~~~~~~~~~~~~~~~~
Abstract base class for resolvers and the resolver registry.

A resolver's job is: given a Track + Album, return a ResolvedSource
(a URL that the downloader can fetch) or None if it can't find one.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type

from musicdl.core.models import Album, ResolvedSource, Track

logger = logging.getLogger(__name__)

# Global registry: resolver name → class
_REGISTRY: Dict[str, Type["BaseResolver"]] = {}


def register_resolver(cls: Type["BaseResolver"]) -> Type["BaseResolver"]:
    """Class decorator that registers a resolver by its `name` attribute."""
    _REGISTRY[cls.name] = cls
    logger.debug("Registered resolver: %s", cls.name)
    return cls


def build_resolver_chain(names: List[str]) -> List["BaseResolver"]:
    """
    Instantiate resolvers in the order given by *names*.
    Unknown names are logged and skipped.
    """
    chain: List[BaseResolver] = []
    for name in names:
        cls = _REGISTRY.get(name)
        if cls is None:
            logger.warning("Unknown resolver %r — skipping", name)
            continue
        chain.append(cls())
        logger.debug("Added resolver to chain: %s", name)
    return chain


class BaseResolver(ABC):
    """Abstract resolver. Subclasses must set `name` and implement `resolve`."""

    name: str = ""

    @abstractmethod
    def resolve(self, track: Track, album: Album) -> Optional[ResolvedSource]:
        """
        Try to find a downloadable source for *track* in *album*.
        Return a ResolvedSource on success, or None if nothing found.
        """
        ...
