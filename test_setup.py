"""
test_setup.py - Check that everything is installed correctly
Run this before using musicdl
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

REQUIRED = [
    ("musicbrainzngs", "pip install musicbrainzngs"),
    ("tenacity",        "pip install tenacity"),
    ("yaml",            "pip install pyyaml"),
    ("mutagen",         "pip install mutagen"),
    ("yt_dlp",          "pip install yt-dlp"),
]

OPTIONAL = [
    ("aiohttp",  "pip install aiohttp   (faster async downloads)"),
    ("aiofiles", "pip install aiofiles  (faster async downloads)"),
    ("rich",     "pip install rich      (pretty progress bars & tables)"),
]

print("=" * 55)
print("  musicdl — dependency check")
print("=" * 55)

all_ok = True

print("\n[Required]")
for module, hint in REQUIRED:
    try:
        __import__(module)
        print(f"  ✅ {module}")
    except ImportError:
        print(f"  ❌ {module}  →  {hint}")
        all_ok = False

print("\n[Optional]")
for module, hint in OPTIONAL:
    try:
        __import__(module)
        print(f"  ✅ {module}")
    except ImportError:
        print(f"  ⚠️  {module}  →  {hint}")

print("\n[Project modules]")
mods = [
    "musicdl.core.exceptions",
    "musicdl.core.models",
    "musicdl.config.settings",
    "musicdl.metadata.cache",
    "musicdl.metadata.artwork",
    "musicdl.metadata.musicbrainz",
    "musicdl.metadata.tagger",
    "musicdl.metadata.similar",
    "musicdl.download.organizer",
    "musicdl.download.downloader",
    "musicdl.download.pipeline",
    "musicdl.resolvers.base",
    "musicdl.resolvers.ytdlp",
    "musicdl.resolvers.spotify",
    "musicdl.library.database",
    "musicdl.library.manager",
    "musicdl.ui.progress",
]
for mod in mods:
    try:
        __import__(mod)
        print(f"  ✅ {mod}")
    except ImportError as e:
        print(f"  ❌ {mod}  →  {e}")
        all_ok = False

print()
if all_ok:
    print("✅ All good! Try:")
    print('   python main.py help')
    print('   python main.py download "Drake" --album "Take Care" --dry-run')
else:
    print("❌ Fix errors above, then try again.")
    print("   pip install musicbrainzngs tenacity pyyaml mutagen yt-dlp aiohttp aiofiles rich")
