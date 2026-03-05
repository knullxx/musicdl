"""
musicdl.metadata.musicbrainz
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
MusicBrainz metadata client.

Wraps musicbrainzngs to fetch:
  - Artist search & lookup
  - Full release group / release / track listings

All network calls are cached. Rate-limiting is applied via _throttle()
and augmented with tenacity retry logic for transient failures.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import musicbrainzngs as mb
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from musicdl.core.exceptions import (
    AlbumNotFoundError,
    ArtistNotFoundError,
    MetadataError,
)
from musicdl.core.models import Album, Artist, ReleaseType, Track
from musicdl.metadata.cache import MetadataCache

logger = logging.getLogger(__name__)

# MusicBrainz allows 1 request/second without authentication
_MB_DELAY = 1.1   # slightly over 1s to be polite


class MusicBrainzClient:
    """MusicBrainz client with transparent caching and rate limiting."""

    def __init__(
        self,
        cache: MetadataCache,
        app_name: str = "musicdl",
        app_version: str = "1.0.0",
        contact: str = "https://github.com/musicdl/musicdl",
        rate_limit_delay: float = _MB_DELAY,
    ) -> None:
        self._cache        = cache
        self._rate_delay   = rate_limit_delay
        self._last_request = 0.0
        mb.set_useragent(app_name, app_version, contact)
        logger.debug("MusicBrainz client ready (%s %s)", app_name, app_version)

    # ── Rate limiting ─────────────────────────────────────────────────────

    def _throttle(self) -> None:
        """Block until sufficient time has elapsed since the last request."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._rate_delay:
            time.sleep(self._rate_delay - elapsed)
        self._last_request = time.monotonic()

    # ── Artist search ─────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(MetadataError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def search_artist(self, query: str, limit: int = 5) -> List[Artist]:
        """
        Search for artists matching *query*.

        Returns up to *limit* results sorted by MusicBrainz relevance.
        Raises ArtistNotFoundError if no results are returned.
        """
        cache_key = f"mb:artist_search:{query.lower().strip()}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Artist search cache hit for %r", query)
            return [Artist(**a) for a in cached]

        logger.debug("MB artist search: %r (limit=%d)", query, limit)
        self._throttle()
        try:
            result = mb.search_artists(artist=query, limit=limit)
        except mb.NetworkError as exc:
            raise MetadataError(f"MusicBrainz network error: {exc}") from exc
        except mb.ResponseError as exc:
            raise MetadataError(f"MusicBrainz API error: {exc}") from exc

        raw_list = result.get("artist-list", [])
        if not raw_list:
            raise ArtistNotFoundError(query)

        artists = [
            Artist(
                mbid=a["id"],
                name=a["name"],
                sort_name=a.get("sort-name", ""),
                country=a.get("country"),
                disambiguation=a.get("disambiguation"),
            )
            for a in raw_list
        ]

        self._cache.set(cache_key, [
            {
                "mbid": a.mbid,
                "name": a.name,
                "sort_name": a.sort_name,
                "country": a.country,
                "disambiguation": a.disambiguation,
            }
            for a in artists
        ])
        return artists

    # ── Discography ────────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(MetadataError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def list_releases(self, artist: Artist) -> List[dict]:
        """
        Quickly fetch just titles, years, types and mbids for all releases.
        Makes only 1-2 API calls total (paged). No track details fetched.
        """
        cache_key = f"mb:release_list:{artist.mbid}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Release list cache hit for %s", artist.name)
            return cached

        groups: List[dict] = []
        offset = 0
        limit  = 100
        while True:
            self._throttle()
            try:
                result = mb.browse_release_groups(
                    artist=artist.mbid,
                    limit=limit,
                    offset=offset,
                )
            except (mb.NetworkError, mb.ResponseError) as exc:
                raise MetadataError(f"Error listing releases: {exc}") from exc

            batch = result.get("release-group-list", [])
            groups.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        releases = []
        for rg in groups:
            primary_type = rg.get("primary-type", "")
            rtype = ReleaseType.from_mb(primary_type) if primary_type else ReleaseType.OTHER
            title = rg.get("title") or "Unknown"
            rg_id = rg.get("id")
            # first-release-date is returned directly on the release group
            year = self._extract_year(rg.get("first-release-date", ""))

            releases.append({
                "title":        title,
                "year":         year,
                "release_type": rtype.value,
                "mbid":         rg_id,
                "release_id":   None,  # fetched on demand in get_album_details
            })

        releases.sort(key=lambda r: (r["year"] is None, r["year"] or 0))
        self._cache.set(cache_key, releases)
        logger.info("Listed %d releases for %s", len(releases), artist.name)
        return releases

    def get_album_details(self, release_info: dict, artist: Artist) -> Optional[Album]:
        """
        Fetch full track listing for a single release.
        Call this only for the album the user actually wants to download.
        """
        cache_key = f"mb:album_detail:{release_info['mbid']}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            result = self._deserialise_albums([cached], artist)
            return result[0] if result else None

        rtype = ReleaseType(release_info.get("release_type", "other"))
        rg_id = release_info["mbid"]
        title = release_info["title"]
        year  = release_info.get("year")

        release_id = release_info.get("release_id")

        # If we don't have a release_id from the fast list, fetch it
        if not release_id:
            self._throttle()
            try:
                detail = mb.get_release_group_by_id(rg_id, includes=["releases"])
                release_list = detail.get("release-group", {}).get("release-list", [])
                best = self._pick_best_release(release_list)
                if not best:
                    return None
                release_id = best.get("id")
                year = year or self._extract_year(best.get("date", ""))
            except (mb.NetworkError, mb.ResponseError) as exc:
                raise MetadataError(f"Could not fetch release group {rg_id}: {exc}") from exc

        if not release_id:
            return None

        self._throttle()
        try:
            full = mb.get_release_by_id(release_id, includes=["recordings", "labels"])
        except (mb.NetworkError, mb.ResponseError) as exc:
            raise MetadataError(f"Could not fetch release {release_id}: {exc}") from exc

        release_data = full.get("release", {})
        tracks = self._extract_tracks(release_data)
        if not tracks:
            return None

        label = None
        for li in release_data.get("label-info-list", []):
            lname = li.get("label", {}).get("name")
            if lname:
                label = lname
                break

        album = Album(
            title=title,
            artist=artist,
            year=year,
            release_type=rtype,
            tracks=tuple(tracks),
            mbid=rg_id,
            label=label,
            country=release_data.get("country"),
        )
        self._cache.set(cache_key, self._serialise_albums([album])[0])
        return album

    def get_discography(
        self,
        artist: Artist,
        release_types: Optional[List[ReleaseType]] = None,
    ) -> List[Album]:
        """
        Fetch the full discography for *artist*.

        BUG FIX: Cache key now includes release_types so that filtered
        and unfiltered queries don't collide in the cache.
        """
        type_suffix = (
            "_".join(sorted(t.value for t in release_types))
            if release_types
            else "all"
        )
        cache_key = f"mb:discography:{artist.mbid}:{type_suffix}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Discography cache hit for %s (%s)", artist.name, type_suffix)
            return self._deserialise_albums(cached, artist)

        release_groups = self._get_all_release_groups(artist)
        albums: List[Album] = []

        for rg in release_groups:
            primary_type = rg.get("primary-type", "")
            rtype = ReleaseType.from_mb(primary_type) if primary_type else ReleaseType.OTHER
            if release_types and rtype not in release_types:
                continue

            try:
                album = self._release_group_to_album(rg, artist, rtype)
                if album:
                    albums.append(album)
            except (MetadataError, AlbumNotFoundError) as exc:
                logger.warning("Skipping %r: %s", rg.get("title"), exc)

        # Sort chronologically (None years last)
        albums.sort(key=lambda a: (a.year is None, a.year or 0))

        self._cache.set(cache_key, self._serialise_albums(albums))
        logger.info("Fetched %d releases for %s", len(albums), artist.name)
        return albums

    def _get_all_release_groups(self, artist: Artist) -> List[dict]:
        """Page through all release groups for an artist, unfiltered."""
        groups: List[dict] = []
        offset = 0
        limit  = 100

        while True:
            self._throttle()
            try:
                result = mb.browse_release_groups(
                    artist=artist.mbid,
                    limit=limit,
                    offset=offset,
                )
            except mb.NetworkError as exc:
                raise MetadataError(f"Network error fetching release groups: {exc}") from exc
            except mb.ResponseError as exc:
                raise MetadataError(f"API error fetching release groups: {exc}") from exc

            batch = result.get("release-group-list", [])
            groups.extend(batch)

            if len(batch) < limit:
                break
            offset += limit

        logger.debug("Found %d release groups for %s", len(groups), artist.name)
        return groups

    def _release_group_to_album(
        self,
        rg: dict,
        artist: Artist,
        rtype: ReleaseType,
    ) -> Optional[Album]:
        """
        Resolve one release group → Album by picking the best release and
        fetching its full track listing.
        """
        rg_id = rg.get("id")
        if not rg_id:
            return None
        title = rg.get("title") or "Unknown"

        # Step 1: get the list of releases in this group
        self._throttle()
        try:
            detail = mb.get_release_group_by_id(rg_id, includes=["releases"])
        except (mb.NetworkError, mb.ResponseError) as exc:
            raise MetadataError(
                f"Could not fetch release group {rg_id!r}: {exc}"
            ) from exc

        releases = detail.get("release-group", {}).get("release-list", [])
        if not releases:
            return None

        release = self._pick_best_release(releases)
        if not release:
            return None

        release_id = release.get("id")
        if not release_id:
            return None

        year = self._extract_year(release.get("date", ""))

        # Step 2: fetch the full release with recordings
        self._throttle()
        try:
            full = mb.get_release_by_id(
                release_id,
                includes=["recordings", "labels"],
            )
        except (mb.NetworkError, mb.ResponseError) as exc:
            raise MetadataError(
                f"Could not fetch release {release_id!r}: {exc}"
            ) from exc

        release_data = full.get("release", {})
        tracks = self._extract_tracks(release_data)
        if not tracks:
            return None

        genres = tuple(
            g["name"]
            for g in release_data.get("genre-list", [])[:5]
            if g.get("name")
        )

        label: Optional[str] = None
        for li in release_data.get("label-info-list", []):
            lname = li.get("label", {}).get("name")
            if lname:
                label = lname
                break

        return Album(
            title=title,
            artist=artist,
            year=year,
            release_type=rtype,
            tracks=tuple(tracks),
            mbid=rg_id,
            genres=genres,
            label=label,
            country=release_data.get("country"),
        )

    # ── Static helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _pick_best_release(releases: List[dict]) -> Optional[dict]:
        """
        Prefer official releases with dates; fall back to anything available.
        Priority: official+dated > official > dated > any
        """
        official = [r for r in releases if r.get("status", "").lower() == "official"]
        dated_official = [r for r in official if r.get("date")]
        dated_any      = [r for r in releases if r.get("date")]

        for pool in (dated_official, official, dated_any, releases):
            if pool:
                return pool[0]
        return None

    @staticmethod
    def _extract_year(date_str: str) -> Optional[int]:
        """Extract 4-digit year from a YYYY, YYYY-MM, or YYYY-MM-DD string."""
        if not date_str:
            return None
        try:
            return int(date_str.split("-")[0])
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _extract_tracks(release_data: dict) -> List[Track]:
        """Extract sorted Track objects from a full release dict."""
        tracks: List[Track] = []
        for medium in release_data.get("medium-list", []):
            try:
                disc_num = int(medium.get("position", 1))
            except (ValueError, TypeError):
                disc_num = 1

            for t in medium.get("track-list", []):
                rec = t.get("recording") or {}

                try:
                    pos_int = int(t.get("position", 0))
                except (ValueError, TypeError):
                    pos_int = 0

                length = rec.get("length")
                try:
                    length_ms: Optional[int] = int(length) if length else None
                except (ValueError, TypeError):
                    length_ms = None

                isrc_list = rec.get("isrc-list") or []
                isrc = isrc_list[0] if isrc_list else None

                # Track title from the track object takes priority over recording title
                title = (
                    t.get("title")
                    or rec.get("title")
                    or "Unknown Track"
                )

                tracks.append(Track(
                    title=title,
                    track_number=pos_int,
                    disc_number=disc_num,
                    duration_ms=length_ms,
                    mbid=rec.get("id"),
                    isrc=isrc,
                ))

        tracks.sort(key=lambda t: (t.disc_number, t.track_number))
        return tracks

    # ── Serialisation ──────────────────────────────────────────────────────

    @staticmethod
    def _serialise_albums(albums: List[Album]) -> List[dict]:
        return [
            {
                "title":        a.title,
                "year":         a.year,
                "release_type": a.release_type.value,
                "mbid":         a.mbid,
                "genres":       list(a.genres),
                "label":        a.label,
                "country":      a.country,
                "tracks": [
                    {
                        "title":        t.title,
                        "track_number": t.track_number,
                        "disc_number":  t.disc_number,
                        "duration_ms":  t.duration_ms,
                        "mbid":         t.mbid,
                        "isrc":         t.isrc,
                    }
                    for t in a.tracks
                ],
            }
            for a in albums
        ]

    @staticmethod
    def _deserialise_albums(data: List[dict], artist: Artist) -> List[Album]:
        albums = []
        for a in data:
            tracks = tuple(Track(**t) for t in a.get("tracks", []))
            albums.append(Album(
                title=a["title"],
                artist=artist,
                year=a.get("year"),
                release_type=ReleaseType(a.get("release_type", "other")),
                tracks=tracks,
                mbid=a.get("mbid"),
                genres=tuple(a.get("genres", [])),
                label=a.get("label"),
                country=a.get("country"),
            ))
        return albums
