from pathlib import Path

import pytest

from reminder_bot.config import ConfigError, load_config


def environ(tmp_path: Path, **overrides: str) -> dict[str, str]:
    return {
        "BOT_TOKEN": "123:abc",
        "DATABASE_PATH": str(tmp_path / "data" / "reminders.db"),
        "BACKUP_DIR": str(tmp_path / "backups"),
        **overrides,
    }


def test_reads_values_and_creates_folders(tmp_path: Path) -> None:
    config = load_config(environ(tmp_path, LOG_LEVEL="debug"))
    assert config.bot_token == "123:abc"
    assert config.database_path.parent.is_dir()
    assert config.backup_dir.is_dir()
    assert config.heartbeat_path == tmp_path / "data" / "heartbeat"
    assert config.log_level == "DEBUG"


@pytest.mark.parametrize("token", ["", "   "])
def test_missing_token_is_a_clear_error(tmp_path: Path, token: str) -> None:
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        load_config(environ(tmp_path, BOT_TOKEN=token))


def test_unwritable_location_is_a_clear_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    with pytest.raises(ConfigError, match="write"):
        load_config(environ(tmp_path, DATABASE_PATH=str(blocker / "reminders.db")))


def test_error_does_not_contain_the_token(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    with pytest.raises(ConfigError) as caught:
        load_config(environ(tmp_path, BOT_TOKEN="SECRET", BACKUP_DIR=str(blocker / "b")))
    assert "SECRET" not in str(caught.value)
