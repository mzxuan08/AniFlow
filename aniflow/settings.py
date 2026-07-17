from __future__ import annotations

import os
import shutil
from pathlib import Path


def validate_download_directory(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("下载目录必须是绝对路径")
    path = path.resolve()
    forbidden = {Path("/"), Path("/etc"), Path("/usr"), Path("/bin"), Path("/var")}
    if path in forbidden:
        raise ValueError("不能使用系统目录作为下载目录")
    path.mkdir(parents=True, exist_ok=True)
    if not os.access(path, os.W_OK):
        raise ValueError("下载目录不可写")
    return path


def has_minimum_free_space(path: Path, minimum_gb: float) -> bool:
    probe = path if path.exists() else path.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free >= minimum_gb * 1024**3
