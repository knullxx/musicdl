"""
musicdl.core.exceptions
~~~~~~~~~~~~~~~~~~~~~~~~
All custom exceptions used throughout musicdl.
"""


class MusicdlError(Exception):
    """Base exception for all musicdl errors."""


class ConfigError(MusicdlError):
    """Raised for invalid or unreadable configuration."""


class MetadataError(MusicdlError):
    """Raised when metadata retrieval fails."""


class ArtistNotFoundError(MetadataError):
    """Raised when no artist matches the search query."""
    def __init__(self, query: str):
        super().__init__(f"No artist found for query: {query!r}")
        self.query = query


class AlbumNotFoundError(MetadataError):
    """Raised when an album or release cannot be resolved."""
    def __init__(self, identifier: str):
        super().__init__(f"Album not found: {identifier!r}")
        self.identifier = identifier


class DownloadError(MusicdlError):
    """Raised when a download fails."""


class ResolverError(MusicdlError):
    """Raised when no resolver can find a source for a track."""


class PathTraversalError(MusicdlError):
    """Raised when a constructed path would escape the output directory."""
    def __init__(self, path: str):
        super().__init__(f"Path traversal detected: {path!r}")
        self.path = path


class TaggingError(MusicdlError):
    """Raised when metadata tagging fails."""


class CacheError(MusicdlError):
    """Raised when the metadata cache cannot be read or written."""
