import pytest

from aniflow.settings import has_minimum_free_space, validate_download_directory
from aniflow.store import Store


def test_setting_round_trip(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'test.db'}")
    store.create_schema()

    store.set_setting("download_dir", str(tmp_path / "media"))

    assert store.get_setting("download_dir") == str(tmp_path / "media")


def test_download_directory_must_be_safe_absolute_path(tmp_path):
    assert validate_download_directory(str(tmp_path / "media")) == (tmp_path / "media").resolve()
    with pytest.raises(ValueError):
        validate_download_directory("relative/media")
    with pytest.raises(ValueError):
        validate_download_directory("/")


def test_minimum_free_space_uses_configured_gigabytes(tmp_path, monkeypatch):
    usage = type("Usage", (), {"free": 4 * 1024**3})()
    monkeypatch.setattr("aniflow.settings.shutil.disk_usage", lambda _path: usage)

    assert has_minimum_free_space(tmp_path, 3.5) is True
    assert has_minimum_free_space(tmp_path, 5) is False
