"""
musicdl.ui.progress
~~~~~~~~~~~~~~~~~~~~
Progress display. Uses `rich` if installed for beautiful output,
falls back to plain text if not.
"""

from __future__ import annotations

import sys
from typing import Optional

_RICH = False
try:
    from rich.console import Console
    from rich.progress import (
        BarColumn, DownloadColumn, Progress, SpinnerColumn,
        TaskID, TextColumn, TimeRemainingColumn, TransferSpeedColumn,
    )
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from rich.text import Text
    _RICH = True
except ImportError:
    pass


# ── Plain text fallback ───────────────────────────────────────────────────────

def print_header():
    print("\n" + "="*60)
    print("  musicdl — music downloader")
    print("="*60)


def print_section(title: str):
    print(f"\n{'─'*40}")
    print(f"  {title}")
    print(f"{'─'*40}")


def print_success(msg: str):
    print(f"  ✅ {msg}")


def print_error(msg: str):
    print(f"  ❌ {msg}")


def print_warning(msg: str):
    print(f"  ⚠️  {msg}")


def print_info(msg: str):
    print(f"  ℹ️  {msg}")


def print_track_progress(track_title: str, current: int, total: int):
    pct = int((current / total) * 100) if total > 0 else 0
    bar_len = 30
    filled  = int(bar_len * pct / 100)
    bar     = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  [{bar}] {pct:>3}%  {track_title[:40]:<40}", end="", flush=True)


def print_track_done(track_title: str):
    print(f"\r  ✅ {track_title[:55]:<55}")


# ── Rich table helpers ────────────────────────────────────────────────────────

def print_album_table(albums: list):
    """Print a numbered table of albums."""
    if _RICH:
        console = Console()
        table   = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("#",            style="dim", width=4)
        table.add_column("Year",         style="yellow", width=6)
        table.add_column("Title",        style="bold white", min_width=30)
        table.add_column("Type",         style="cyan", width=12)
        table.add_column("Tracks",       style="green", width=7)
        for i, a in enumerate(albums, 1):
            year   = str(a.get("year") or a.get("year", "")) if isinstance(a, dict) else (str(a.year) if a.year else "")
            title  = a.get("title") if isinstance(a, dict) else a.title
            rtype  = a.get("release_type") if isinstance(a, dict) else a.release_type.value
            tracks = str(a.get("track_count", "")) if isinstance(a, dict) else str(len(a.tracks))
            table.add_row(str(i), year or "????", title, rtype, tracks)
        console.print(table)
    else:
        print(f"\n{'#':>4}  {'Year':<6}  {'Title':<45}  {'Type':<12}  Tracks")
        print("─" * 80)
        for i, a in enumerate(albums, 1):
            year   = str(a.get("year") or "") if isinstance(a, dict) else (str(a.year) if a.year else "????")
            title  = a.get("title") if isinstance(a, dict) else a.title
            rtype  = a.get("release_type") if isinstance(a, dict) else a.release_type.value
            tracks = str(a.get("track_count", "")) if isinstance(a, dict) else str(len(a.tracks))
            print(f"  {i:>3}.  {year or '????':<6}  {title:<45}  {rtype:<12}  {tracks}")


def print_library_stats(stats: dict):
    """Print library statistics."""
    dur_ms  = stats.get("total_duration_ms", 0)
    hours   = dur_ms // 3_600_000
    minutes = (dur_ms % 3_600_000) // 60_000

    if _RICH:
        console = Console()
        table   = Table(box=box.SIMPLE, show_header=False)
        table.add_column("Key",   style="cyan")
        table.add_column("Value", style="bold white")
        table.add_row("Artists", str(stats.get("artists", 0)))
        table.add_row("Albums",  str(stats.get("albums",  0)))
        table.add_row("Tracks",  str(stats.get("tracks",  0)))
        table.add_row("Total duration", f"{hours}h {minutes}m")
        console.print(Panel(table, title="[bold]Library Stats[/bold]", border_style="cyan"))
    else:
        print_section("Library Stats")
        print(f"  Artists : {stats.get('artists', 0)}")
        print(f"  Albums  : {stats.get('albums',  0)}")
        print(f"  Tracks  : {stats.get('tracks',  0)}")
        print(f"  Duration: {hours}h {minutes}m")


def print_artist_list(artists: list):
    if _RICH:
        console = Console()
        table   = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("#",       style="dim",        width=4)
        table.add_column("Artist",  style="bold white", min_width=25)
        table.add_column("Country", style="yellow",     width=10)
        for i, a in enumerate(artists, 1):
            table.add_row(str(i), a["name"], a.get("country") or "")
        console.print(table)
    else:
        for i, a in enumerate(artists, 1):
            country = f" [{a['country']}]" if a.get("country") else ""
            print(f"  {i:>3}. {a['name']}{country}")


def print_similar_artists(similar: list):
    if _RICH:
        console = Console()
        table   = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("#",          style="dim",   width=4)
        table.add_column("Artist",     style="bold white", min_width=25)
        table.add_column("Relation",   style="cyan",  width=20)
        for i, a in enumerate(similar, 1):
            table.add_row(str(i), a["name"], a.get("relation", ""))
        console.print(table)
    else:
        for i, a in enumerate(similar, 1):
            print(f"  {i:>3}. {a['name']}  ({a.get('relation', '')})")
