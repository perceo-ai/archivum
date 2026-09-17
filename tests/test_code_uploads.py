"""Unpacking an archive a client produced.

This is the one place in Archivum that writes a tree of files chosen by
somebody else, so most of these tests are about refusing archives rather than
accepting them.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from archivum.code_uploads import (
    UploadError,
    staging_dir,
    unpack_repo_archive,
)


def _archive(tmp_path: Path, members: dict[str, bytes], *, name: str = "repo.tar.gz") -> Path:
    path = tmp_path / name
    with tarfile.open(path, "w:gz") as tar:
        for member_name, data in members.items():
            info = tarfile.TarInfo(member_name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def _archive_with(tmp_path: Path, info: tarfile.TarInfo, data: bytes = b"") -> Path:
    path = tmp_path / "repo.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return path


def test_a_normal_repository_unpacks(tmp_path):
    archive = _archive(tmp_path, {"src/main.py": b"print('hi')\n", "README.md": b"# hi\n"})
    destination = tmp_path / "out"

    report = unpack_repo_archive(archive, destination)

    assert report.files == 2
    assert (destination / "src" / "main.py").read_text() == "print('hi')\n"


def test_an_absolute_path_is_refused(tmp_path):
    archive = _archive(tmp_path, {"/etc/passwd": b"root\n"})

    with pytest.raises(UploadError, match="absolute"):
        unpack_repo_archive(archive, tmp_path / "out")


def test_a_traversing_path_is_refused(tmp_path):
    """The classic: a member that writes outside the directory it was given."""
    archive = _archive(tmp_path, {"../../escaped.txt": b"owned\n"})

    with pytest.raises(UploadError, match="traverse"):
        unpack_repo_archive(archive, tmp_path / "out")

    assert not (tmp_path.parent / "escaped.txt").exists()


def test_a_symlink_is_refused(tmp_path):
    """A symlink out of the tree turns every later write through it into a
    write anywhere on the server's disk."""
    info = tarfile.TarInfo("link")
    info.type = tarfile.SYMTYPE
    info.linkname = "/etc/passwd"

    with pytest.raises(UploadError, match="links"):
        unpack_repo_archive(_archive_with(tmp_path, info), tmp_path / "out")


def test_a_hard_link_is_refused(tmp_path):
    info = tarfile.TarInfo("link")
    info.type = tarfile.LNKTYPE
    info.linkname = "src/main.py"

    with pytest.raises(UploadError, match="links"):
        unpack_repo_archive(_archive_with(tmp_path, info), tmp_path / "out")


def test_a_device_entry_is_refused(tmp_path):
    info = tarfile.TarInfo("dev")
    info.type = tarfile.CHRTYPE

    with pytest.raises(UploadError, match="device"):
        unpack_repo_archive(_archive_with(tmp_path, info), tmp_path / "out")


def test_a_refused_archive_leaves_nothing_behind(tmp_path):
    """A half-unpacked tree would be indexed as if it were the whole repo."""
    archive = _archive(tmp_path, {"good.py": b"ok\n", "../escape.py": b"bad\n"})
    destination = tmp_path / "out"

    with pytest.raises(UploadError):
        unpack_repo_archive(archive, destination)

    assert not destination.exists()


def test_an_empty_archive_is_refused(tmp_path):
    """Otherwise a client bug reads as 'this repository has no code'."""
    archive = tmp_path / "empty.tar.gz"
    with tarfile.open(archive, "w:gz"):
        pass

    with pytest.raises(UploadError, match="no files"):
        unpack_repo_archive(archive, tmp_path / "out")


def test_an_oversized_expansion_is_refused(tmp_path, monkeypatch):
    """A gzip bomb declares a small archive and expands enormously."""
    monkeypatch.setattr("archivum.code_uploads.MAX_UNPACKED_BYTES", 10)
    archive = _archive(tmp_path, {"big.txt": b"x" * 100})

    with pytest.raises(UploadError, match="expands"):
        unpack_repo_archive(archive, tmp_path / "out")


def test_too_many_members_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("archivum.code_uploads.MAX_MEMBERS", 2)
    archive = _archive(tmp_path, {f"f{i}.py": b"x" for i in range(5)})

    with pytest.raises(UploadError, match="more entries"):
        unpack_repo_archive(archive, tmp_path / "out")


def test_reuploading_replaces_rather_than_merges(tmp_path):
    """A file deleted since the last upload must not survive in the index."""
    destination = tmp_path / "out"
    unpack_repo_archive(_archive(tmp_path, {"old.py": b"gone\n"}), destination)

    unpack_repo_archive(
        _archive(tmp_path, {"new.py": b"here\n"}, name="second.tar.gz"), destination
    )

    assert not (destination / "old.py").exists()
    assert (destination / "new.py").exists()


def test_staging_directories_are_scoped_per_vault_and_repo(tmp_path):
    a = staging_dir(tmp_path, wiki_id="default", repo_name="archivum")
    b = staging_dir(tmp_path, wiki_id="other", repo_name="archivum")

    assert a != b


def test_a_staging_name_cannot_escape_the_upload_root(tmp_path):
    with pytest.raises(UploadError, match="escapes"):
        staging_dir(tmp_path, wiki_id="default", repo_name="../../etc")
