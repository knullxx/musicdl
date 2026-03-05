"""
musicdl.config.settings
~~~~~~~~~~~~~~~~~~~~~~~~
Configuration system backed by ~/.musicdl/config.yaml.

Priority (highest → lowest):
  1. CLI flags / environment variables
  2. User config file (~/.musicdl/config.yaml)
  3. Built-in defaults

The Settings object is a plain dataclass; no global singletons.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

import yaml

from musicdl.core.exceptions import ConfigError


_DEFAULT_CONFIG_PATH = Path.home() / ".musicdl" / "config.yaml"
_DEFAULT_OUTPUT_DIR  = Path.home() / "Music"


@dataclass
class Settings:
    """All runtime-configurable options for musicdl."""

    # Paths
    output_dir: Path = field(default_factory=lambda: _DEFAULT_OUTPUT_DIR)
    config_path: Path = field(default_factory=lambda: _DEFAULT_CONFIG_PATH)

    # Download behaviour
    max_threads: int = 4
    audio_format: str = "mp3"          # mp3 | m4a | flac | opus
    audio_quality: str = "320k"        # e.g. "320k", "256k", "128k"
    skip_existing: bool = True
    dry_run: bool = False
    download_artwork: bool = True
    embed_metadata: bool = True
    resume_downloads: bool = True

    # Resolvers (ordered by preference)
    enabled_resolvers: List[str] = field(
        default_factory=lambda: ["ytdlp", "soundcloud"]
    )

    # Network
    request_timeout: int = 30          # seconds
    max_retries: int = 3
    retry_delay: float = 2.0           # base delay in seconds (exponential backoff)
    rate_limit_delay: float = 1.0      # polite delay between metadata API calls

    # MusicBrainz
    mb_app_name: str = "musicdl"
    mb_app_version: str = "1.0.0"
    mb_contact_url: str = "https://github.com/musicdl/musicdl"

    # Cache
    cache_dir: Path = field(
        default_factory=lambda: Path.home() / ".musicdl" / "cache"
    )
    cache_ttl_hours: int = 72

    # Logging
    log_level: str = "INFO"
    log_file: Optional[Path] = None

    # ── Serialisation helpers ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        raw = asdict(self)
        # Convert Path objects to strings for YAML
        for key, val in raw.items():
            if isinstance(val, Path):
                raw[key] = str(val)
        return raw

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        path_fields = {"output_dir", "config_path", "cache_dir", "log_file"}
        coerced: dict = {}
        for key, val in data.items():
            if key in path_fields and val is not None:
                coerced[key] = Path(val)
            else:
                coerced[key] = val
        # Filter unknown keys (forward-compat)
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        coerced = {k: v for k, v in coerced.items() if k in valid}
        return cls(**coerced)


# ── Loader ────────────────────────────────────────────────────────────────────

def load_settings(config_path: Optional[Path] = None) -> Settings:
    """
    Load settings from the YAML config file.

    Returns default Settings if the file does not exist yet.
    Raises ConfigError on parse failures.
    """
    path = config_path or _DEFAULT_CONFIG_PATH

    if not path.exists():
        return Settings(config_path=path)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {path} must be a YAML mapping")

    try:
        return Settings.from_dict(raw)
    except TypeError as exc:
        raise ConfigError(f"Invalid config values in {path}: {exc}") from exc


def save_settings(settings: Settings) -> None:
    """Persist settings to the YAML config file."""
    path = settings.config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(settings.to_dict(), fh, default_flow_style=False)
    except OSError as exc:
        raise ConfigError(f"Cannot write config file {path}: {exc}") from exc


def init_config(settings: Settings) -> None:
    """
    Ensure all required directories exist.
    Call once at application startup.
    """
    for directory in (settings.output_dir, settings.cache_dir):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(f"Cannot create directory {directory}: {exc}") from exc

    if settings.log_file:
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
