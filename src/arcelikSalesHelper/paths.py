from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from .constants import APP_NAME, COMPANY_NAME, DATA_DIR_ENV_VAR, DB_FILENAME


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    db_path: Path
    backup_dir: Path
    log_path: Path


def resolve_paths(env: Mapping[str, str] | None = None) -> AppPaths:
    """Pure resolution, no filesystem access.

    Windows: %LOCALAPPDATA%\\<Company>\\<App>.  Linux: $XDG_DATA_HOME/<App>
    (falling back to ~/.local/share/<App>), handled by platformdirs.
    """
    environ = os.environ if env is None else env
    override = environ.get(DATA_DIR_ENV_VAR)
    if override:
        data_dir = Path(override)
    else:
        author = COMPANY_NAME if sys.platform == "win32" else False
        data_dir = Path(platformdirs.user_data_dir(APP_NAME, appauthor=author))
    return AppPaths(
        data_dir=data_dir,
        db_path=data_dir / DB_FILENAME,
        backup_dir=data_dir / "backups",
        log_path=data_dir / "app.log",
    )


def ensure_dirs(paths: AppPaths) -> AppPaths:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.backup_dir.mkdir(parents=True, exist_ok=True)
    return paths
