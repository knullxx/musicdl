"""
musicdl - Advanced Music Downloader CLI
=======================================
Usage: python main.py <command> [options]

Commands:
  download   Download music by artist, album, or Spotify URL
  search     Search and browse without downloading
  list       List your downloaded library
  stats      Show library statistics
  similar    Find artists similar to one you like
  duplicates Find duplicate tracks in your library
  scan       Import existing music folder into library
  config     Show current configuration
  help       Show detailed help

Run: python main.py help  for full usage guide
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from musicdl.config.settings import load_settings, init_config
from musicdl.utils import setup_logging
from musicdl.ui.progress import (
    print_header, print_section, print_success, print_error,
    print_warning, print_info, print_album_table, print_library_stats,
    print_artist_list, print_similar_artists,
)


# ── Help text ─────────────────────────────────────────────────────────────────

HELP_TEXT = """
╔══════════════════════════════════════════════════════════════╗
║              musicdl — Advanced Music Downloader             ║
╚══════════════════════════════════════════════════════════════╝

COMMANDS
────────

  download    Download music
  search      Browse an artist's discography without downloading
  list        List your downloaded library
  stats       Show library statistics (artists, albums, tracks, duration)
  similar     Discover artists similar to one you like
  duplicates  Find duplicate tracks in your library
  scan        Import an existing music folder into the library
  config      Show current settings
  help        Show this help message

────────────────────────────────────────────────────────────────
DOWNLOAD EXAMPLES
────────────────────────────────────────────────────────────────

  # Download a specific album
  python main.py download "Drake" --album "Take Care"

  # Download a single track
  python main.py download "Drake" --track "God's Plan"

  # Download entire discography
  python main.py download "Drake"

  # Download from a Spotify link (album, playlist, or track)
  python main.py download --spotify "https://open.spotify.com/album/xxx"

  # Preview without downloading (dry run)
  python main.py download "Drake" --album "Take Care" --dry-run

  # Download as FLAC at best quality
  python main.py download "Drake" --album "Take Care" --format flac

  # Save to a custom folder
  python main.py download "Drake" --album "Take Care" --output "D:\\Music"

  # Filter by release type
  python main.py download "Drake" --type album
  python main.py download "Drake" --type ep
  python main.py download "Drake" --type single

  # Limit to N most recent releases
  python main.py download "Drake" --limit 3

  # Skip artwork download
  python main.py download "Drake" --no-artwork

  # Re-tag existing files with correct metadata
  python main.py download "Drake" --album "Take Care" --retag

────────────────────────────────────────────────────────────────
OTHER COMMANDS
────────────────────────────────────────────────────────────────

  # Search an artist's discography
  python main.py search "Kendrick Lamar"

  # List all downloaded albums
  python main.py list

  # Search your library
  python main.py list --query "take care"

  # Library stats
  python main.py stats

  # Find similar artists
  python main.py similar "Drake"

  # Find duplicate tracks
  python main.py duplicates

  # Scan and import existing music folder
  python main.py scan --dir "C:\\Users\\you\\Music"

  # Show current config
  python main.py config

────────────────────────────────────────────────────────────────
OUTPUT FORMATS:  mp3 (default)  |  flac  |  m4a  |  opus
QUALITY:         320k (default) |  256k  |  128k
────────────────────────────────────────────────────────────────
"""


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="musicdl",
        description="Advanced music downloader",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", default="help",
                        choices=["download", "search", "list", "stats",
                                 "similar", "duplicates", "scan", "config", "help"])

    # Positional artist name (optional)
    parser.add_argument("artist", nargs="?", default=None)

    # Download options
    parser.add_argument("--album",     metavar="NAME",  help="Target a specific album")
    parser.add_argument("--track",     metavar="NAME",  help="Download a single track")
    parser.add_argument("--spotify",   metavar="URL",   help="Spotify track/album/playlist URL")
    parser.add_argument("--format",    default=None,    choices=["mp3","flac","m4a","opus"], help="Audio format")
    parser.add_argument("--quality",   default=None,    choices=["320k","256k","128k","best"],     help="Audio quality")
    parser.add_argument("--output",    metavar="DIR",   help="Custom output directory")
    parser.add_argument("--type",      default=None,    choices=["album","ep","single","compilation","live","all"], help="Filter release type")
    parser.add_argument("--limit",     type=int,        default=None, metavar="N", help="Max number of releases to download")
    parser.add_argument("--dry-run",   action="store_true", help="Preview without downloading")
    parser.add_argument("--no-artwork",action="store_true", help="Skip artwork download")
    parser.add_argument("--no-tags",   action="store_true", help="Skip metadata tagging")
    parser.add_argument("--retag",     action="store_true", help="Re-tag existing files")
    parser.add_argument("--query",     metavar="TEXT",  help="Search query for list command")

    # Scan command
    parser.add_argument("--dir", metavar="DIR", dest="scan_dir", help="Directory to scan (for scan command)")

    # Global options
    parser.add_argument("--log-level", default=None, choices=["DEBUG","INFO","WARNING"])
    parser.add_argument("-h", "--help", action="store_true", help="Show help")

    return parser


# ── Shared setup ──────────────────────────────────────────────────────────────

def get_clients(settings):
    from musicdl.metadata.musicbrainz import MusicBrainzClient
    from musicdl.metadata.cache import MetadataCache
    cache = MetadataCache(settings.cache_dir, ttl_hours=settings.cache_ttl_hours)
    mb = MusicBrainzClient(
        cache=cache,
        app_name=settings.mb_app_name,
        app_version=settings.mb_app_version,
        contact=settings.mb_contact_url,
    )
    return mb, cache


def pick_artist(mb, query: str):
    """Search for an artist and let user pick one."""
    print_info(f"Searching for artist: {query!r}")
    try:
        artists = mb.search_artist(query, limit=8)
    except Exception as e:
        print_error(f"Artist search failed: {e}")
        sys.exit(1)

    print(f"\n  Found {len(artists)} result(s):")
    for i, a in enumerate(artists):
        disambig = f" — {a.disambiguation}" if a.disambiguation else ""
        country  = f" [{a.country}]"         if a.country        else ""
        print(f"    {i+1}. {a.name}{disambig}{country}")

    if len(artists) == 1:
        return artists[0]

    try:
        choice = input(f"\n  Pick an artist (1-{len(artists)}): ").strip()
        return artists[int(choice) - 1]
    except (ValueError, IndexError):
        return artists[0]


def fetch_and_filter_releases(mb, artist, args):
    """Fetch release list and apply type/limit filters."""
    print_info("Fetching release list...")
    try:
        releases = mb.list_releases(artist)
    except Exception as e:
        print_error(f"Failed to fetch releases: {e}")
        sys.exit(1)

    if not releases:
        print_warning("No releases found. Try picking a different artist.")
        sys.exit(0)

    # Filter by type
    if args.type and args.type != "all":
        releases = [r for r in releases if r["release_type"] == args.type]
        if not releases:
            print_warning(f"No releases of type '{args.type}' found.")
            sys.exit(0)

    # Filter by album name
    if args.album:
        matched = [r for r in releases if args.album.lower() in r["title"].lower()]
        if not matched:
            print_error(f"No album matching '{args.album}' found.")
            print("\n  Available releases:")
            for r in releases[:20]:
                print(f"    {r['year'] or '????'}  {r['title']}")
            sys.exit(1)
        elif len(matched) == 1:
            releases = matched
            print_success(f"Found: {matched[0]['title']} ({matched[0]['year'] or '????'})")
        else:
            print(f"\n  Found {len(matched)} matching releases:")
            print_album_table(matched)
            try:
                choice = input(f"\n  Pick one (1-{len(matched)}): ").strip()
                releases = [matched[int(choice) - 1]]
            except (ValueError, IndexError):
                releases = [matched[0]]

    return releases


def fetch_album_details(mb, releases, artist):
    """Fetch full track details for chosen releases."""
    print_info(f"Fetching track details for {len(releases)} release(s)...")
    albums = []
    for r in releases:
        try:
            album = mb.get_album_details(r, artist)
            if album:
                albums.append(album)
                print_success(f"{album.title} — {len(album.tracks)} tracks")
            else:
                print_warning(f"Skipped {r['title']} (no tracks found)")
        except Exception as e:
            print_warning(f"Could not fetch {r['title']}: {e}")
    return albums


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_download(args, settings):
    from musicdl.download.pipeline import DownloadPipeline
    from musicdl.library.manager import LibraryManager
    from musicdl.resolvers.spotify import is_spotify_url, extract_spotify_tracks

    # Apply flag overrides to settings
    if args.format:     settings.audio_format    = args.format
    if args.quality:
        # Normalise: always store with 'k' suffix (e.g. "320k"), except "best"
        q = args.quality
        if q != "best" and not q.endswith("k"):
            q = q + "k"
        settings.audio_quality = q
    if args.output:     settings.output_dir      = Path(args.output)
    if args.no_artwork: settings.download_artwork = False
    if args.no_tags:    settings.embed_metadata  = False
    # --retag: disable skip_existing so we reprocess already-downloaded files
    if args.retag:      settings.skip_existing   = False

    # ── Spotify path ──────────────────────────────────────────────────────
    if args.spotify or (args.artist and is_spotify_url(args.artist)):
        url = args.spotify or args.artist
        print_info(f"Processing Spotify URL...")
        tracks = extract_spotify_tracks(url)
        if not tracks:
            print_error("Could not extract tracks from Spotify URL.")
            print_info("Make sure yt-dlp supports Spotify or try a direct artist/album search.")
            sys.exit(1)

        print_success(f"Found {len(tracks)} track(s) from Spotify")
        mb, _ = get_clients(settings)
        albums = []
        seen_albums = {}

        for t in tracks:
            artist_name = t.get("artist", "")
            album_name  = t.get("album", "")
            if not artist_name:
                continue
            key = f"{artist_name}::{album_name}"
            if key in seen_albums:
                continue
            seen_albums[key] = True

            try:
                artists = mb.search_artist(artist_name, limit=1)
                if not artists:
                    continue
                artist = artists[0]
                releases = mb.list_releases(artist)
                if album_name:
                    releases = [r for r in releases if album_name.lower() in r["title"].lower()]
                if releases:
                    album = mb.get_album_details(releases[0], artist)
                    if album:
                        albums.append(album)
                        print_success(f"Queued: {album.title} by {artist.name}")
            except Exception as e:
                print_warning(f"Could not resolve {artist_name} - {album_name}: {e}")

        if not albums:
            print_error("Could not resolve any albums from Spotify tracks.")
            sys.exit(1)

    # ── Standard artist path ──────────────────────────────────────────────
    else:
        if not args.artist:
            print_error("Please provide an artist name or Spotify URL.")
            print_info('Usage: python main.py download "Artist Name"')
            sys.exit(1)

        mb, _ = get_clients(settings)
        artist   = pick_artist(mb, args.artist)
        print_success(f"Selected: {artist.name}")

        # ── Single track path ──────────────────────────────────────────────
        if args.track:
            print_info(f"Searching for track: {args.track!r}")
            try:
                album = mb.find_track(artist, args.track)
            except Exception as e:
                print_error(f"Track search failed: {e}")
                sys.exit(1)

            if not album:
                print_error(f"Could not find track '{args.track}' by {artist.name}")
                print_info("Try checking the spelling or use --album to download the full album")
                sys.exit(1)

            track = album.tracks[0]
            print_success(f"Found: {track.title} — from {album.title} ({album.year or '????'})")
            albums = [album]

        else:
            releases = fetch_and_filter_releases(mb, artist, args)

            # If no specific album, show list and let user pick
            if not args.album:
                print_section(f"Releases for {artist.name}")
                print_album_table(releases)
                print("\n  Enter a number to pick ONE release, or press Enter for ALL:")
                choice = input("  Choice: ").strip()
                if choice:
                    try:
                        releases = [releases[int(choice) - 1]]
                        print_success(f"Selected: {releases[0]['title']}")
                    except (ValueError, IndexError):
                        print_warning("Invalid choice, downloading all.")

            # Apply limit
            if args.limit:
                releases = releases[:args.limit]

            albums = fetch_album_details(mb, releases, artist)

    if not albums:
        print_error("No downloadable albums found.")
        sys.exit(1)

    total_tracks = sum(len(a.tracks) for a in albums)

    # ── Dry run ───────────────────────────────────────────────────────────
    if args.dry_run:
        print_section("Dry Run Preview")
        for a in albums:
            print(f"  📀 {a.title} ({a.year or '????'}) — {len(a.tracks)} tracks")
            if len(albums) <= 3:
                for t in a.tracks:
                    print(f"       {t.track_number:>2}. {t.title}")
        print()
        print_info(f"Would download {total_tracks} tracks to {settings.output_dir}")
        print_info("Remove --dry-run to actually download.")
        return

    confirm = input(f"\n  Download {total_tracks} tracks to {settings.output_dir}? [y/N] ").strip().lower()
    if confirm != "y":
        print_info("Aborted.")
        return

    # ── Run pipeline ──────────────────────────────────────────────────────
    def on_progress(task, done, total):
        from musicdl.ui.progress import print_track_progress
        print_track_progress(task.track.title, done, total)

    pipeline = DownloadPipeline(settings)
    result   = pipeline.run(albums, on_progress=on_progress)

    # Register in library
    db_path = settings.cache_dir.parent / "library.db"
    lib = LibraryManager(db_path)
    registered = lib.register_completed_tasks(result.tasks)
    lib.close()

    print_section("Download Complete")
    print_success(f"{result.completed} downloaded")
    if result.skipped: print_info(f"{result.skipped} skipped (already existed)")
    if result.failed:  print_warning(f"{result.failed} failed")
    print_info(f"Success rate: {result.success_rate:.1f}%")
    print_info(f"Files saved to: {settings.output_dir}")
    if registered:     print_info(f"Registered {registered} tracks in library")


def cmd_search(args, settings):
    if not args.artist:
        print_error("Please provide an artist name.")
        print_info('Usage: python main.py search "Artist Name"')
        sys.exit(1)

    mb, _ = get_clients(settings)
    artist   = pick_artist(mb, args.artist)
    print_success(f"Selected: {artist.name}")

    print_info("Fetching release list...")
    try:
        releases = mb.list_releases(artist)
    except Exception as e:
        print_error(f"Failed: {e}")
        sys.exit(1)

    if not releases:
        print_warning("No releases found.")
        return

    # Apply type filter
    if args.type and args.type != "all":
        releases = [r for r in releases if r["release_type"] == args.type]

    print_section(f"{artist.name} — {len(releases)} release(s)")
    print_album_table(releases)
    print()
    print_info(f"To download one: python main.py download \"{args.artist}\" --album \"<title>\"")
    print_info(f"To download all: python main.py download \"{args.artist}\"")


def cmd_list(args, settings):
    from musicdl.library.manager import LibraryManager
    db_path = settings.cache_dir.parent / "library.db"
    lib = LibraryManager(db_path)

    query = args.query or (args.artist if args.command == "list" else None)
    albums = lib.list_albums(query)
    lib.close()

    if not albums:
        if query:
            print_warning(f"No albums matching '{query}' in your library.")
        else:
            print_warning("Your library is empty. Download some music first!")
            print_info('Try: python main.py download "Drake" --album "Take Care"')
        return

    print_section(f"Library — {len(albums)} album(s)" + (f" matching '{query}'" if query else ""))
    print_album_table(albums)


def cmd_stats(args, settings):
    from musicdl.library.manager import LibraryManager
    db_path = settings.cache_dir.parent / "library.db"
    lib = LibraryManager(db_path)
    stats = lib.stats()
    lib.close()
    print_library_stats(stats)


def cmd_similar(args, settings):
    if not args.artist:
        print_error("Please provide an artist name.")
        print_info('Usage: python main.py similar "Drake"')
        sys.exit(1)

    mb, _ = get_clients(settings)
    artist = pick_artist(mb, args.artist)
    print_success(f"Selected: {artist.name}")

    from musicdl.metadata.similar import get_similar_artists
    print_info("Fetching similar artists...")
    similar = get_similar_artists(artist.mbid, limit=15)

    if not similar:
        print_warning("No similar artists found in MusicBrainz for this artist.")
        return

    print_section(f"Artists similar to {artist.name}")
    print_similar_artists(similar)
    print()
    print_info("To download one: python main.py download \"<artist name>\"")


def cmd_duplicates(args, settings):
    from musicdl.library.manager import LibraryManager
    db_path = settings.cache_dir.parent / "library.db"
    lib = LibraryManager(db_path)
    dupes = lib.find_duplicates()
    lib.close()

    if not dupes:
        print_success("No duplicates found in your library!")
        return

    print_section(f"Found {len(dupes)} duplicate(s)")
    for d in dupes:
        print(f"\n  Title    : {d['title']}")
        for path in d["paths"].split("|"):
            print(f"  File     : {path}")


def cmd_scan(args, settings):
    # Accept: python main.py scan --dir "C:\Music"
    # or:     python main.py scan "C:\Music"  (artist arg used as fallback)
    scan_dir = args.scan_dir or args.artist
    if not scan_dir:
        print_error("Please provide a directory to scan.")
        print_info('Usage: python main.py scan --dir "C:\\Users\\you\\Music"')
        sys.exit(1)

    path = Path(scan_dir)
    if not path.exists():
        print_error(f"Directory not found: {path}")
        sys.exit(1)

    from musicdl.library.manager import LibraryManager
    db_path = settings.cache_dir.parent / "library.db"
    lib = LibraryManager(db_path)

    print_info(f"Scanning {path}...")
    found = lib.scan_directory(path)
    lib.close()

    if found:
        print_success(f"Imported {found} new tracks into library")
    else:
        print_info("No new tracks found (everything already in library)")


def cmd_config(args, settings):
    print_section("Current Configuration")
    print(f"  Output directory : {settings.output_dir}")
    print(f"  Audio format     : {settings.audio_format}")
    print(f"  Audio quality    : {settings.audio_quality}")
    print(f"  Max threads      : {settings.max_threads}")
    print(f"  Skip existing    : {settings.skip_existing}")
    print(f"  Download artwork : {settings.download_artwork}")
    print(f"  Embed metadata   : {settings.embed_metadata}")
    print(f"  Cache directory  : {settings.cache_dir}")
    print(f"  Config file      : {settings.config_path}")
    print()
    print_info(f"Edit config at: {settings.config_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args   = parser.parse_args()

    if args.help or args.command == "help":
        print(HELP_TEXT)
        return

    settings = load_settings()
    if args.log_level:
        settings.log_level = args.log_level
    setup_logging(settings.log_level)
    init_config(settings)

    try:
        dispatch = {
            "download":   cmd_download,
            "search":     cmd_search,
            "list":       cmd_list,
            "stats":      cmd_stats,
            "similar":    cmd_similar,
            "duplicates": cmd_duplicates,
            "scan":       cmd_scan,
            "config":     cmd_config,
        }
        fn = dispatch.get(args.command)
        if fn:
            fn(args, settings)
        else:
            print(HELP_TEXT)

    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logging.getLogger("musicdl").exception("Unhandled exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
