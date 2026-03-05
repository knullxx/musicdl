# musicdl 🎵

A command-line tool to download music by artist or album, with automatic metadata tagging and album artwork.

Built with Python, [yt-dlp](https://github.com/yt-dlp/yt-dlp), and the [MusicBrainz](https://musicbrainz.org/) API.

---

## Features

- Search any artist by name
- Browse their full discography instantly
- Download a specific album or entire discography
- YouTube + SoundCloud as sources (automatic fallback)
- Automatically embeds metadata (title, artist, album, track number, year)
- Downloads album artwork and embeds it in files
- Skips already-downloaded tracks automatically
- Caches MusicBrainz lookups so repeat searches are instant
- Organizes files into `Music/Artist/Album (Year)/` folders
- Handles explicit track names (profanity filter for search queries)
- SQLite library to track everything you've downloaded
- Pretty tables and progress bars (with `rich`)


---

## Requirements

- Python 3.8+
- [FFmpeg](https://ffmpeg.org/download.html) — required for audio conversion

---

## Installation

**1. Clone the repo**
```bash
git clone https://github.com/knullxx/musicdl.git
cd musicdl
```

**2. Install Python dependencies**
```bash
pip install -r requirements.txt
```


**3. Install FFmpeg**

- **Windows:**
  ```powershell
  winget install ffmpeg
  ```
- **Mac:**
  ```bash
  brew install ffmpeg
  ```
- **Linux:**
  ```bash
  sudo apt install ffmpeg
  ```

**4. Verify setup**
```bash
python test_setup.py
```

---

## Usage

### Show help
```bash
python main.py help
```

### Download a specific album
```bash
python main.py download "Drake" --album "Take Care"
```
### Download a single track
```bash
python main.py download "Drake" --track "God's Plan"
```
### Browse full discography and pick
```bash
python main.py download "Drake"
```

### Dry run (preview without downloading)
```bash
python main.py download "Drake" --album "Take Care" --dry-run
```

### Download as FLAC
```bash
python main.py download "Drake" --album "Take Care" --format flac
```

### Save to a custom folder
```bash
python main.py download "Drake" --album "Take Care" --output "D:\Music"
```

### Filter by release type
```bash
python main.py download "Drake" --type album
python main.py download "Drake" --type ep
python main.py download "Drake" --type single
```

### Limit to N releases
```bash
python main.py download "Drake" --limit 3
```

### Re-tag existing files
```bash
python main.py download "Drake" --album "Take Care" --retag
```

---

## Other Commands

```bash
# Search without downloading
python main.py search "Kendrick Lamar"

# List your downloaded library
python main.py list

# Search your library
python main.py list --query "take care"

# Library stats
python main.py stats

# Find similar artists
python main.py similar "Drake"

# Find duplicate tracks
python main.py duplicates

# Import existing music folder
python main.py scan --dir "C:\Users\you\Music"

# Show current config
python main.py config
```

---

## Output

Files are saved to `~/Music/` by default:

```
Music/
└── Drake/
    └── Take Care (2011)/
        ├── cover.jpg
        ├── 01 Take Care.mp3
        ├── 02 Crew Love.mp3
        └── ...
```

---

## Project Structure

```
musicdl/
├── core/
│   ├── models.py        # Data classes (Artist, Album, Track, etc.)
│   └── exceptions.py    # Custom exceptions
├── config/
│   └── settings.py      # Configuration
├── metadata/
│   ├── musicbrainz.py   # MusicBrainz API client
│   ├── tagger.py        # Embeds ID3/MP4/FLAC/OGG tags
│   ├── artwork.py       # Downloads album art
│   ├── cache.py         # Disk-based metadata cache
│   └── similar.py       # Similar artist suggestions
├── download/
│   ├── pipeline.py      # Orchestrates the full download flow
│   ├── downloader.py    # Async yt-dlp downloader
│   └── organizer.py     # Builds folder structure and file paths
├── resolvers/
│   ├── base.py          # Abstract resolver base class
│   ├── ytdlp.py         # YouTube resolver
│   ├── soundcloud.py    # SoundCloud resolver (fallback)
│   └── spotify.py       # Spotify URL parser
├── library/
│   ├── database.py      # SQLite library database
│   └── manager.py       # Library search, scan, dedup, stats
├── ui/
│   └── progress.py      # Pretty tables and progress bars
└── utils/
    └── __init__.py      # Shared helpers
main.py                  # CLI entry point
test_setup.py            # Dependency checker
```

---

## Configuration

Settings live in `~/.musicdl/config.yaml`:

```yaml
output_dir: ~/Music
audio_format: mp3        # mp3, m4a, flac, opus
audio_quality: 320k
max_threads: 4
skip_existing: true
download_artwork: true
embed_metadata: true
```

---

## Troubleshooting

**No releases found** — Try picking a different number from the artist list. There may be multiple artists with the same name.

**FFmpeg not found** — Install FFmpeg and make sure it's on your PATH.

**Track skipped** — The track couldn't be found on YouTube or SoundCloud. Try again later or check if it's available online.

**Slow first run** — MusicBrainz is rate-limited to 1 req/sec. Results are cached after the first run so it's instant next time.

---

## Disclaimer

This tool is for personal and educational use only. Only download music you have the right to access.

## Issues
Found a bug? Open an issue on [GitHub](https://github.com/knullxx/musicdl/issues)
---

## License

MIT
