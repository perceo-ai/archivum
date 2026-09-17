"""Receive a repository from a machine the server cannot read.

Indexing resolves paths on the server. That is right when the repository lives
there and impossible otherwise, which is every machine a developer actually
codes on. The fix is not to teach the pipeline to read a remote disk — it is to
put the files where the pipeline already looks.

The client walks its own repository, honours `.gitignore`, and uploads what it
chose. The server unpacks that into a staging directory and runs the existing
indexer against it unchanged. No second code path, and nothing here knows how
to parse a language.

Unpacking an archive someone else produced is the dangerous part of this file.
Every member is checked before anything is written, and the checks are refusals
rather than sanitisations: a member that has to be rewritten to be safe is a
member we did not expect, and guessing what it meant is how this goes wrong.
"""

from __future__ import annotations

import tarfile
from dataclasses import dataclass
from pathlib import Path

# A repository of text is small; anything near this is not what we think it is.
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_UNPACKED_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 50_000


class UploadError(Exception):
    """An uploaded archive was malformed, unsafe, or too large."""


@dataclass(frozen=True)
class UnpackReport:
    files: int
    bytes: int


def staging_dir(cache_root: Path, *, wiki_id: str, repo_name: str) -> Path:
    """Where an uploaded repository lands.

    Separated from the index cache by a directory of its own so that clearing
    uploads can never take a cache with it, and vice versa.
    """
    target = (cache_root / "uploads" / wiki_id / repo_name).resolve()
    root = (cache_root / "uploads").resolve()
    if not target.is_relative_to(root):
        raise UploadError("Upload path escapes the upload root")
    return target


def _refuse(member: tarfile.TarInfo, reason: str) -> UploadError:
    return UploadError(f"Refused '{member.name}': {reason}")


def _check(member: tarfile.TarInfo, destination: Path) -> Path:
    """Validate one member and return where it may be written."""
    name = member.name
    if name.startswith("/") or name.startswith("\\"):
        raise _refuse(member, "absolute paths are not allowed")
    if ".." in Path(name).parts:
        raise _refuse(member, "paths may not traverse upwards")
    # Links are the other half of a traversal escape: a symlink pointing out of
    # the tree turns every later write through it into a write anywhere.
    if member.issym() or member.islnk():
        raise _refuse(member, "links are not allowed")
    if member.isdev() or member.isfifo():
        raise _refuse(member, "device and fifo entries are not allowed")
    if not (member.isfile() or member.isdir()):
        raise _refuse(member, "only regular files and directories are allowed")

    target = (destination / name).resolve()
    if not target.is_relative_to(destination):
        raise _refuse(member, "path escapes the destination")
    return target


def unpack_repo_archive(archive: Path, destination: Path) -> UnpackReport:
    """Unpack an uploaded repository archive into `destination`.

    The destination is replaced rather than merged: a re-upload that left the
    previous upload's deleted files behind would index code that no longer
    exists, and the stale entries would be indistinguishable from real ones.
    """
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise UploadError("Archive is larger than this server accepts")

    destination = destination.resolve()
    if destination.exists():
        _remove_tree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    files = 0
    written = 0
    try:
        with tarfile.open(archive, mode="r:gz") as tar:
            for index, member in enumerate(tar):
                if index >= MAX_MEMBERS:
                    raise UploadError("Archive contains more entries than this server accepts")
                target = _check(member, destination)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                # Counted as we go rather than from the header alone: a gzip
                # bomb declares a small size and expands on extraction.
                written += member.size
                if written > MAX_UNPACKED_BYTES:
                    raise UploadError("Archive expands to more than this server accepts")
                source = tar.extractfile(member)
                if source is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as handle:
                    while chunk := source.read(1024 * 1024):
                        handle.write(chunk)
                target.chmod(0o644)
                files += 1
    except tarfile.TarError as exc:
        _remove_tree(destination)
        raise UploadError(f"Archive could not be read: {exc}") from exc
    except UploadError:
        # A refused archive must leave nothing behind: a half-unpacked tree
        # would otherwise be indexed as if it were the whole repository.
        _remove_tree(destination)
        raise

    if files == 0:
        _remove_tree(destination)
        raise UploadError("Archive contained no files")

    return UnpackReport(files=files, bytes=written)


def _remove_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
