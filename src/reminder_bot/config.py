"""Reads and validates environment variables (see contracts/runtime-config.md)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """The bot can't start with this configuration. The message is safe to show."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_path: Path
    backup_dir: Path
    log_level: str

    @property
    def heartbeat_path(self) -> Path:
        return self.database_path.parent / "heartbeat"


def _ensure_writable(directory: Path) -> None:
    probe = directory / ".write-check"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe.touch()
        probe.unlink()
    except OSError as error:
        raise ConfigError(f"Can't write to {directory}: {error}") from error


def load_config(environ: Mapping[str, str] = os.environ) -> Config:
    token = environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN is required. Get one from @BotFather.")

    database_path = Path(environ.get("DATABASE_PATH") or "/data/reminders.db")
    backup_dir = Path(environ.get("BACKUP_DIR") or "/data/backups")
    _ensure_writable(database_path.parent)
    _ensure_writable(backup_dir)

    return Config(
        bot_token=token,
        database_path=database_path,
        backup_dir=backup_dir,
        log_level=(environ.get("LOG_LEVEL") or "INFO").upper(),
    )
