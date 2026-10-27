"""Exclusive, never-overwriting writes in the media volume (plan section 4.4).

The volume layout uses UUIDs and version numbers only, never a title,
an author name or an email (plan section 4.1). Nothing here replaces an
existing file or directory:

* directories are created with ``exist_ok=False``;
* files are created with ``O_CREAT | O_EXCL``, so a second writer fails
  with ``FileExistsError`` instead of overwriting.

When a write fails halfway, the partial file is removed — it is always a
file this very call created, never one that existed before.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import UUID

from django.conf import settings

#: Directories ``0750`` and files ``0640`` (plan section 4.1).
DIRECTORY_MODE = 0o750
FILE_MODE = 0o640

logger = logging.getLogger(__name__)

#: Read size for hashing and copying; keeps memory flat for 50 MB files.
CHUNK_SIZE = 1024 * 1024


def private_root() -> Path:
    """``<MEDIA_ROOT>/private``: the root every stored private path is relative to.

    It is the directory Nginx exposes as ``/_protected/`` (plan section 4.6).
    """
    return Path(settings.MEDIA_ROOT) / "private"


def private_path(relative: str | PurePosixPath) -> Path:
    """Absolute path of a path stored relative to the private volume."""
    return private_root() / relative


def catalog_root() -> Path:
    """``<MEDIA_ROOT>/public/catalog``: the root every public copy path is relative to.

    It is the directory Nginx exposes as ``/_catalog/`` (plan section 4.6).
    """
    return Path(settings.MEDIA_ROOT) / "public" / "catalog"


def catalog_relative_path(manuscript_id: UUID, version_id: UUID) -> PurePosixPath:
    """``<manuscript_uuid>/<version_uuid>.pdf`` under the catalog root (plan section 4.7)."""
    return PurePosixPath(str(manuscript_id), f"{version_id}.pdf")


def catalog_path(relative: str | PurePosixPath) -> Path:
    """Absolute path of a path stored relative to the public catalog."""
    return catalog_root() / relative


def version_relative_dir(manuscript_id: UUID, version_number: int) -> PurePosixPath:
    """``manuscripts/<manuscript_uuid>/v0001``."""
    return PurePosixPath("manuscripts", str(manuscript_id), f"v{version_number:04d}")


def version_dir(manuscript_id: UUID, version_number: int) -> Path:
    """Absolute directory of a version."""
    return private_path(version_relative_dir(manuscript_id, version_number))


def allocate_version_dir(manuscript_id: UUID, version_number: int) -> Path:
    """Create the directory of a version; fails if it already exists.

    Previous versions are never renamed, reused or overwritten.
    """
    path = version_dir(manuscript_id, version_number)
    path.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=False)
    return path


@contextmanager
def open_exclusive(path: Path) -> Iterator[BinaryIO]:
    """Open ``path`` for writing, failing if it already exists.

    If the body raises, the partial file is deleted. ``FileExistsError``
    is raised before anything is created, so an existing file is never
    touched.
    """
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def write_exclusive(path: Path, data: bytes | Iterable[bytes]) -> None:
    """Write bytes (or an iterable of chunks) to a brand-new file."""
    chunks = [data] if isinstance(data, bytes) else data
    with open_exclusive(path) as handle:
        for chunk in chunks:
            handle.write(chunk)


@dataclass(frozen=True)
class CopyResult:
    """Size and SHA-256 of a copied file, computed while copying."""

    size_bytes: int
    sha256: str


def copy_exclusive(source: Path, destination: Path) -> CopyResult:
    """Copy ``source`` to a NEW file, hashing it in the same pass.

    The copy is byte for byte; ``FileExistsError`` if ``destination``
    exists. It is an independent file, never a link to ``source``.
    """
    digest = hashlib.sha256()
    size = 0
    with open_exclusive(destination) as handle:
        for chunk in iter_file_chunks(source):
            digest.update(chunk)
            size += len(chunk)
            handle.write(chunk)
    return CopyResult(size_bytes=size, sha256=digest.hexdigest())


def iter_file_chunks(path: Path, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    """Read a file in chunks."""
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            yield chunk


def draft_relative_path(user_id: UUID, draft_id: UUID) -> PurePosixPath:
    """``drafts/<user_uuid>/<draft_uuid>.pdf`` (plan section 4.1)."""
    return PurePosixPath("drafts", str(user_id), f"{draft_id}.pdf")


def upload_tmp_path(upload_id: UUID) -> Path:
    """Staging file in ``tmp/uploads``; the directory is created if missing."""
    directory = Path(settings.MEDIA_ROOT) / "tmp" / "uploads"
    directory.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    return directory / f"{upload_id}.part"


def move_exclusive(source: Path, destination: Path) -> None:
    """Move ``source`` to a NEW ``destination`` without ever overwriting.

    ``os.replace`` would silently overwrite; a hard link fails with
    ``FileExistsError`` atomically when the destination exists. The
    source name is dropped afterwards, so the file ends up with a single
    name (both paths live in the same volume).
    """
    destination.parent.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    os.link(source, destination)
    source.unlink()


def remove_quietly(path: Path | None) -> None:
    """Best-effort delete of a file this process owns; never raises."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("No se pudo eliminar el archivo %s", path.name, exc_info=True)
