from pathlib import Path

from arcelikSalesHelper.constants import (
    APP_NAME,
    DATA_DIR_ENV_VAR,
    DB_FILENAME,
)
from arcelikSalesHelper.paths import ensure_dirs, resolve_paths


def test_env_override_is_used(tmp_path: Path) -> None:
    paths = resolve_paths({DATA_DIR_ENV_VAR: str(tmp_path / "data")})
    assert paths.data_dir == tmp_path / "data"
    assert paths.db_path == tmp_path / "data" / DB_FILENAME
    assert paths.backup_dir == tmp_path / "data" / "backups"


def test_default_location_ends_with_app_name() -> None:
    assert resolve_paths({}).data_dir.name == APP_NAME


def test_resolve_has_no_side_effects_and_ensure_creates_dirs(
    tmp_path: Path,
) -> None:
    paths = resolve_paths({DATA_DIR_ENV_VAR: str(tmp_path / "x" / "y")})
    assert not paths.data_dir.exists()
    ensure_dirs(paths)
    ensure_dirs(paths)  # idempotent
    assert paths.data_dir.is_dir() and paths.backup_dir.is_dir()
