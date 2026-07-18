from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable


class LibtorrentEngine:
    def __init__(
        self,
        state_dir: Path,
        on_status: Callable[..., None] | None = None,
        on_health: Callable[..., None] | None = None,
    ) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.on_status = on_status or (lambda *_args, **_kwargs: None)
        self.on_health = on_health or (lambda *_args, **_kwargs: None)
        self.available = False
        self.error: str | None = None
        self._handles: dict[int, object] = {}
        self._torrent_files: dict[int, list[tuple[Path, int]]] = {}
        self._last_status: dict[int, tuple[str, float, int, str]] = {}
        self._last_health: dict[int, tuple[float, int, int]] = {}
        self._running = False
        try:
            import libtorrent as lt

            self.lt = lt
            self.session = lt.session({"listen_interfaces": "0.0.0.0:6881"})
            self.available = True
        except ImportError:
            self.error = "未安装 python3-libtorrent"

    def add_torrent(self, task_id: int, torrent_data: bytes, save_path: Path) -> None:
        if not self.available:
            raise RuntimeError(self.error or "libtorrent 不可用")
        save_path.mkdir(parents=True, exist_ok=True)
        (self.state_dir / f"{task_id}.torrent").write_bytes(torrent_data)
        info = self.lt.torrent_info(self.lt.bdecode(torrent_data))
        handle = self.session.add_torrent({"ti": info, "save_path": str(save_path)})
        self._handles[task_id] = handle
        files = info.files()
        self._torrent_files[task_id] = [
            ((save_path / files.file_path(index)).resolve(), files.file_size(index))
            for index in range(files.num_files())
        ]
        if not self._running:
            self._running = True
            threading.Thread(target=self._monitor, daemon=True).start()

    def restore(self, task_id: int, save_path: Path) -> None:
        if task_id in self._handles:
            return
        torrent_file = self.state_dir / f"{task_id}.torrent"
        if torrent_file.exists():
            self.add_torrent(task_id, torrent_file.read_bytes(), save_path)

    def _monitor(self) -> None:
        while self._running:
            self._poll_once()
            time.sleep(2)

    def _poll_once(self) -> None:
        last_health = getattr(self, "_last_health", None)
        if last_health is None:
            last_health = self._last_health = {}
        for task_id, handle in list(self._handles.items()):
            status = handle.status()
            state = "已完成" if status.is_seeding else "下载中"
            snapshot = (
                state,
                round(status.progress * 100, 2),
                status.download_rate,
                str(handle.info_hash()),
            )
            if self._last_status.get(task_id) != snapshot:
                self._last_status[task_id] = snapshot
                self.on_status(
                    task_id,
                    state=snapshot[0],
                    progress=snapshot[1],
                    download_rate=snapshot[2],
                    info_hash=snapshot[3],
                )
            health = (
                snapshot[1],
                int(getattr(status, "num_peers", 0)),
                int(getattr(status, "num_seeds", 0)),
            )
            if last_health.get(task_id) != health:
                last_health[task_id] = health
                callback = getattr(self, "on_health", None)
                if callback is not None:
                    callback(
                        task_id,
                        progress=health[0],
                        peer_count=health[1],
                        seed_count=health[2],
                    )

    def pause(self, task_id: int) -> None:
        self._handles[task_id].pause()

    def resume(self, task_id: int) -> None:
        self._handles[task_id].resume()

    def remove(self, task_id: int, delete_files: bool = False) -> None:
        handle = self._handles.pop(task_id, None)
        self._torrent_files.pop(task_id, None)
        self._last_status.pop(task_id, None)
        self._last_health.pop(task_id, None)
        if handle is not None:
            options = self.lt.options_t.delete_files if delete_files else 0
            self.session.remove_torrent(handle, options)
        (self.state_dir / f"{task_id}.torrent").unlink(missing_ok=True)

    def detach(self, task_id: int) -> None:
        handle = self._handles.pop(task_id, None)
        self._torrent_files.pop(task_id, None)
        self._last_status.pop(task_id, None)
        self._last_health.pop(task_id, None)
        if handle is not None:
            self.session.remove_torrent(handle)

    def torrent_files(self, task_id: int, save_path: Path) -> list[Path]:
        loaded = self._torrent_files.get(task_id)
        if loaded is not None:
            return [path for path, _size in loaded]
        torrent_file = self.state_dir / f"{task_id}.torrent"
        if not torrent_file.exists():
            return []
        info = self.lt.torrent_info(self.lt.bdecode(torrent_file.read_bytes()))
        files = info.files()
        return [
            (save_path / files.file_path(index)).resolve()
            for index in range(files.num_files())
        ]

    def incomplete_files(self) -> set[Path]:
        incomplete: set[Path] = set()
        for task_id, handle in list(self._handles.items()):
            files = self._torrent_files.get(task_id, [])
            progress = handle.file_progress()
            incomplete.update(
                path
                for index, (path, size) in enumerate(files)
                if index >= len(progress) or progress[index] < size
            )
        return incomplete

    def configure(self, max_downloads: int, download_limit_kbps: int, upload_limit_kbps: int) -> None:
        self.session.apply_settings({"active_downloads": max_downloads})
        self.session.set_download_rate_limit(download_limit_kbps * 1024)
        self.session.set_upload_rate_limit(upload_limit_kbps * 1024)


class DisabledEngine:
    available = False
    error = "测试模式"

    def add_torrent(self, task_id: int, torrent_data: bytes, save_path: Path) -> None:
        raise RuntimeError(self.error)

    def pause(self, task_id: int) -> None:
        raise RuntimeError(self.error)

    def resume(self, task_id: int) -> None:
        raise RuntimeError(self.error)

    def remove(self, task_id: int, delete_files: bool = False) -> None:
        raise RuntimeError(self.error)

    def restore(self, task_id: int, save_path: Path) -> None:
        return

    def configure(self, max_downloads: int, download_limit_kbps: int, upload_limit_kbps: int) -> None:
        return

    def incomplete_files(self) -> set[Path]:
        return set()

    def detach(self, task_id: int) -> None:
        return

    def torrent_files(self, task_id: int, save_path: Path) -> list[Path]:
        return []
