from __future__ import annotations

import shutil
from pathlib import Path


def archive_torrent_files(
    files: list[Path],
    staging_root: Path,
    library_root: Path,
) -> int:
    source_root = staging_root.resolve()
    target_root = library_root.resolve()
    moved = 0
    for file_path in files:
        source = file_path.resolve()
        try:
            relative = source.relative_to(source_root)
        except ValueError as exc:
            raise ValueError("种子文件超出临时下载目录") from exc
        target = (target_root / relative).resolve()
        if target_root not in target.parents:
            raise ValueError("归档目标超出媒体库目录")
        if source == target:
            continue
        if not source.exists():
            if target.is_file():
                continue
            raise FileNotFoundError(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moved += 1

    _remove_empty_directories(source_root)
    return moved


def _remove_empty_directories(root: Path) -> None:
    if not root.exists():
        return
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass
