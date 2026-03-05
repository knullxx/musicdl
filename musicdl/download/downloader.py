"""
musicdl.download.downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Async downloader that uses yt-dlp to fetch audio files.

Each DownloadTask already has a resolved_url (a YouTube/SoundCloud/etc.
webpage URL). We pass it to yt-dlp with post-processing options to
transcode to the desired format and quality.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable, List, Optional

from musicdl.core.models import DownloadStatus, DownloadTask

logger = logging.getLogger(__name__)

# Callback signature: (task, bytes_done, bytes_total)
ProgressCallback = Callable[[DownloadTask, int, int], None]


class AsyncDownloader:
    """
    Concurrent downloader built on yt-dlp.
    Use as an async context manager.
    """

    def __init__(
        self,
        max_threads: int = 4,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        quality: str = "320k",
        output_format: str = "mp3",
    ) -> None:
        self._max_threads   = max_threads
        self._timeout       = timeout
        self._max_retries   = max_retries
        self._retry_delay   = retry_delay
        self._quality       = quality
        self._output_format = output_format
        self._semaphore: asyncio.Semaphore

    async def __aenter__(self) -> "AsyncDownloader":
        self._semaphore = asyncio.Semaphore(self._max_threads)
        return self

    async def __aexit__(self, *_) -> None:
        pass

    # ── Public ─────────────────────────────────────────────────────────────

    async def download_all(
        self,
        tasks: List[DownloadTask],
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        """Download all *tasks* concurrently (bounded by max_threads)."""
        coros = [self._download_one(t, on_progress) for t in tasks]
        await asyncio.gather(*coros)

    # ── Internal ───────────────────────────────────────────────────────────

    async def _download_one(
        self,
        task: DownloadTask,
        on_progress: Optional[ProgressCallback],
    ) -> None:
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            for attempt in range(1, self._max_retries + 1):
                try:
                    await loop.run_in_executor(
                        None,
                        self._ytdlp_download,
                        task,
                        on_progress,
                    )
                    if task.status == DownloadStatus.COMPLETED:
                        return
                except Exception as exc:
                    logger.warning(
                        "Attempt %d/%d failed for %r: %s",
                        attempt, self._max_retries, task.track.title, exc,
                    )
                    task.error = str(exc)

                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_delay * attempt)

            if task.status != DownloadStatus.COMPLETED:
                task.status = DownloadStatus.FAILED
                logger.error("All attempts failed for: %s", task.track.title)

    def _ytdlp_download(
        self,
        task: DownloadTask,
        on_progress: Optional[ProgressCallback],
    ) -> None:
        """Blocking yt-dlp download. Runs in a thread pool executor."""
        try:
            import yt_dlp
        except ImportError:
            task.status = DownloadStatus.FAILED
            task.error  = "yt-dlp not installed"
            return

        output_path = task.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # yt-dlp requires forward slashes in outtmpl even on Windows
        outtmpl = output_path.with_suffix("").as_posix()

        def progress_hook(d: dict) -> None:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done  = d.get("downloaded_bytes") or 0
                task.bytes_total = total
                task.bytes_done  = done
                if on_progress:
                    on_progress(task, done, total)

        # Build postprocessor — quality: strip 'k', omit if 'best'
        quality_val = self._quality.rstrip("k") if self._quality != "best" else "0"
        ydl_opts = {
            "format":           "bestaudio/best",
            "outtmpl":          outtmpl + ".%(ext)s",
            "quiet":            True,
            "no_warnings":      True,
            "noplaylist":       True,
            "socket_timeout":   self._timeout,
            "progress_hooks":   [progress_hook],
            "postprocessors": [
                {
                    "key":              "FFmpegExtractAudio",
                    "preferredcodec":   self._output_format,
                    "preferredquality": quality_val,
                }
            ],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([task.resolved_url])

            # yt-dlp + FFmpegExtractAudio writes to stem + preferred extension
            expected = output_path.parent / (output_path.stem + f".{self._output_format}")
            if expected.exists():
                # Rename to exact output_path if different
                if expected != output_path:
                    expected.rename(output_path)
                task.status = DownloadStatus.COMPLETED
                logger.info("Downloaded: %s", output_path.name)
            else:
                # Fallback: find any file with the same stem
                matches = [
                    f for f in output_path.parent.iterdir()
                    if f.stem == output_path.stem and f.suffix != ""
                ]
                if matches:
                    matches[0].rename(output_path)
                    task.status = DownloadStatus.COMPLETED
                    logger.info("Downloaded (renamed): %s", output_path.name)
                else:
                    task.status = DownloadStatus.FAILED
                    task.error = "Output file not found after download"
                    logger.error("Expected file not found: %s", expected)

        except Exception as exc:
            task.status = DownloadStatus.FAILED
            task.error  = str(exc)
            logger.error("yt-dlp error for %r: %s", task.track.title, exc)
