import pytest

from aniflow.archive import archive_torrent_files


def test_archive_moves_only_torrent_files_and_preserves_relative_paths(tmp_path):
    staging = tmp_path / "staging" / "Anime"
    library = tmp_path / "library" / "Anime"
    first = staging / "Anime - 01.mp4"
    second = staging / "extras" / "note.txt"
    unrelated = staging / "other.part"
    second.parent.mkdir(parents=True)
    first.write_bytes(b"video")
    second.write_bytes(b"note")
    unrelated.write_bytes(b"keep")

    archive_torrent_files([first, second], staging, library)

    assert (library / "Anime - 01.mp4").read_bytes() == b"video"
    assert (library / "extras" / "note.txt").read_bytes() == b"note"
    assert unrelated.read_bytes() == b"keep"


def test_archive_can_resume_when_target_was_already_moved(tmp_path):
    staging = tmp_path / "staging"
    library = tmp_path / "library"
    target = library / "Anime - 01.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"video")

    archive_torrent_files([staging / "Anime - 01.mp4"], staging, library)

    assert target.read_bytes() == b"video"


def test_archive_rejects_torrent_path_outside_staging_root(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"keep")

    with pytest.raises(ValueError):
        archive_torrent_files([outside], staging, tmp_path / "library")

    assert outside.read_bytes() == b"keep"
