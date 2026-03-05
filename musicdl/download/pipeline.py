"""
musicdl.download.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~
High-level download pipeline orchestrator.

Coordinates:
  1. FileOrganizer  → build DownloadTask list
  2. Resolvers      → find URLs for each pending task
  3. AsyncDownloader → download all tasks in parallel
  4. ArtworkFetcher → download cover art per album
  5. Tagger         → embed metadata into completed files
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from musicdl.config.settings import Settings
from musicdl.core.models import Album, DownloadStatus, DownloadTask

# Define ProgressCallback here so it's always available regardless of optional imports
ProgressCallback = Callable[[DownloadTask, int, int], None]

try:
    from musicdl.download.downloader import AsyncDownloader
except ImportError:
    AsyncDownloader = None  # type: ignore[assignment,misc]
from musicdl.download.organizer import FileOrganizer
try:
    from musicdl.metadata.artwork import ArtworkFetcher
except ImportError:
    ArtworkFetcher = None  # type: ignore[assignment,misc]
try:
    from musicdl.metadata.tagger import tag_file
except ImportError:
    def tag_file(*a, **kw): return False  # type: ignore[misc]
from musicdl.resolvers import build_resolver_chain, resolve_track

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Summary of a completed download pipeline run."""
    total:     int = 0
    completed: int = 0
    skipped:   int = 0
    failed:    int = 0
    # FIX: mutable default via field(), not bare None
    tasks: List[DownloadTask] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        denom = self.total - self.skipped
        return (self.completed / denom * 100) if denom > 0 else 100.0


class DownloadPipeline:
    """Stateless pipeline: construct once, call run() multiple times."""

    def __init__(self, settings: Settings) -> None:
        self._settings  = settings
        self._organizer = FileOrganizer(
            output_dir=settings.output_dir,
            audio_format=settings.audio_format,
            skip_existing=settings.skip_existing,
        )
        self._resolvers = build_resolver_chain(settings.enabled_resolvers)
        self._artwork   = ArtworkFetcher() if ArtworkFetcher is not None else None

    # ── Public entry points ───────────────────────────────────────────────

    def run(
        self,
        albums: List[Album],
        on_progress: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> PipelineResult:
        """Synchronous entry point — safe for CLI use outside an event loop."""
        return asyncio.run(self._run_async(albums, on_progress, dry_run))

    async def run_async(
        self,
        albums: List[Album],
        on_progress: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> PipelineResult:
        """Async entry point for embedding in an existing event loop."""
        return await self._run_async(albums, on_progress, dry_run)

    # ── Core pipeline ─────────────────────────────────────────────────────

    async def _run_async(
        self,
        albums: List[Album],
        on_progress: Optional[ProgressCallback],
        dry_run: bool,
    ) -> PipelineResult:
        s = self._settings

        # Phase 1: Build task list
        all_tasks = self._organizer.build_tasks_for_albums(albums)
        pending   = [t for t in all_tasks if t.status == DownloadStatus.PENDING]
        skipped   = [t for t in all_tasks if t.status == DownloadStatus.SKIPPED]

        logger.info(
            "Pipeline: %d tracks total, %d pending, %d skipped",
            len(all_tasks), len(pending), len(skipped),
        )

        if dry_run:
            logger.info("[dry-run] Would download %d tracks", len(pending))
            for t in pending:
                logger.info("  [dry-run] %s – %s", t.album.title, t.track.title)
            return PipelineResult(
                total=len(all_tasks),
                completed=0,
                skipped=len(skipped),
                failed=0,
                tasks=all_tasks,
            )

        if not pending:
            return PipelineResult(
                total=len(all_tasks),
                completed=0,
                skipped=len(skipped),
                failed=0,
                tasks=all_tasks,
            )

        # Phase 2: Resolve URLs (synchronous — API calls are serial by design)
        logger.info("Resolving URLs for %d tracks…", len(pending))
        self._resolve_all(pending)

        # Phase 3: Download only tasks that were successfully resolved
        downloadable = [t for t in pending if t.status == DownloadStatus.PENDING]

        if downloadable:
            if AsyncDownloader is None:
                logger.error(
                    "aiofiles/aiohttp not installed — cannot download. "
                    "Run: pip install aiofiles aiohttp"
                )
                for t in downloadable:
                    t.status = DownloadStatus.FAILED
                    t.error  = "AsyncDownloader unavailable (missing aiofiles/aiohttp)"
            else:
                async with AsyncDownloader(
                    max_threads=s.max_threads,
                    timeout=s.request_timeout,
                    max_retries=s.max_retries,
                    retry_delay=s.retry_delay,
                    quality=s.audio_quality,
                    output_format=s.audio_format,
                ) as dl:
                    await dl.download_all(downloadable, on_progress=on_progress)

        # Phase 4: Artwork (deduplicated by mbid)
        if s.download_artwork:
            await self._fetch_artwork_for_albums(albums)

        # Phase 5: Embed metadata
        if s.embed_metadata:
            self._tag_completed(pending)

        completed = sum(1 for t in pending if t.status == DownloadStatus.COMPLETED)
        failed    = sum(1 for t in pending if t.status == DownloadStatus.FAILED)

        logger.info(
            "Pipeline done: %d completed, %d failed, %d skipped",
            completed, failed, len(skipped),
        )

        return PipelineResult(
            total=len(all_tasks),
            completed=completed,
            skipped=len(skipped),
            failed=failed,
            tasks=all_tasks,
        )

    def _resolve_all(self, tasks: List[DownloadTask]) -> None:
        """Resolve download URLs for pending tasks."""
        for task in tasks:
            if task.status != DownloadStatus.PENDING:
                continue
            source = resolve_track(task.track, task.album, self._resolvers)
            if source:
                task.resolved_url = source.url
            else:
                task.status = DownloadStatus.FAILED
                task.error  = "No source found by any resolver"
                logger.warning(
                    "No source for: %s – %s",
                    task.album.artist.name,
                    task.track.title,
                )

    async def _fetch_artwork_for_albums(self, albums: List[Album]) -> None:
        """Download cover art for each unique album."""
        if self._artwork is None:
            return
        loop = asyncio.get_running_loop()
        seen: set = set()
        for album in albums:
            if not album.mbid or album.mbid in seen:
                continue
            seen.add(album.mbid)
            art_path = self._organizer.artwork_path(album)
            if art_path.exists():
                continue
            await loop.run_in_executor(
                None, self._download_artwork_sync, album.mbid, art_path
            )

    def _download_artwork_sync(self, mbid: str, dest: Path) -> None:
        if self._artwork is None:
            return
        try:
            url = self._artwork.fetch_url(mbid)
            if url:
                self._artwork.download(url, dest)
        except Exception as exc:
            logger.warning("Artwork download failed for %s: %s", mbid, exc)

    def _tag_completed(self, tasks: List[DownloadTask]) -> None:
        for task in tasks:
            if task.status != DownloadStatus.COMPLETED:
                continue
            if not task.output_path.exists():
                logger.warning("File missing post-download: %s", task.output_path)
                continue
            art_path = self._organizer.artwork_path(task.album)
            ok = tag_file(
                path=task.output_path,
                track=task.track,
                album=task.album,
                artwork_path=art_path if art_path.exists() else None,
            )
            if not ok:
                logger.warning("Tagging failed for %s", task.output_path.name)
