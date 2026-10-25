"""Tests for the exclusive writes in the media volume (TSK-33).

Covers the criterion "nunca sobrescribe un archivo existente": version
directories and files are created exclusively, with the permissions and
the UUID-only layout of the plan (sections 4.1 and 4.4).
"""

from __future__ import annotations

import hashlib
import stat
from uuid import uuid4

import pytest

from apps.publications.services import storage

pytestmark = pytest.mark.usefixtures("media_root")


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def mode_of(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class TestVersionDirectory:
    def test_path_uses_only_the_uuid_and_the_padded_version(self, media_root) -> None:
        manuscript_id = uuid4()

        path = storage.version_dir(manuscript_id, 3)

        assert path == media_root / "private" / "manuscripts" / str(manuscript_id) / "v0003"

    def test_allocation_creates_the_directory_with_mode_0750(self) -> None:
        path = storage.allocate_version_dir(uuid4(), 1)

        assert path.is_dir() and mode_of(path) == 0o750

    def test_allocating_an_existing_version_fails_and_keeps_its_content(self) -> None:
        manuscript_id = uuid4()
        path = storage.allocate_version_dir(manuscript_id, 1)
        (path / "original.pdf").write_bytes(b"v1")

        with pytest.raises(FileExistsError):
            storage.allocate_version_dir(manuscript_id, 1)

        assert (path / "original.pdf").read_bytes() == b"v1"

    def test_versions_live_side_by_side(self) -> None:
        manuscript_id = uuid4()

        first = storage.allocate_version_dir(manuscript_id, 1)
        second = storage.allocate_version_dir(manuscript_id, 2)

        assert first != second and first.parent == second.parent


class TestExclusiveWrite:
    def test_new_file_is_created_with_mode_0640(self, tmp_path) -> None:
        target = tmp_path / "original.pdf"

        storage.write_exclusive(target, b"contenido")

        assert target.read_bytes() == b"contenido" and mode_of(target) == 0o640

    def test_chunks_are_written_in_order(self, tmp_path) -> None:
        target = tmp_path / "streamed.pdf"

        storage.write_exclusive(target, (part for part in (b"ab", b"cd", b"ef")))

        assert target.read_bytes() == b"abcdef"

    def test_existing_file_is_never_overwritten(self, tmp_path) -> None:
        target = tmp_path / "original.pdf"
        target.write_bytes(b"primera version")

        with pytest.raises(FileExistsError):
            storage.write_exclusive(target, b"segunda version")

        assert target.read_bytes() == b"primera version"

    def test_failed_write_removes_only_the_partial_file(self, tmp_path) -> None:
        target = tmp_path / "partial.pdf"

        def broken():
            yield b"parcial"
            raise RuntimeError("disco lleno")

        with pytest.raises(RuntimeError):
            storage.write_exclusive(target, broken())

        assert not target.exists()

    def test_failed_write_never_removes_a_pre_existing_file(self, tmp_path) -> None:
        target = tmp_path / "original.pdf"
        target.write_bytes(b"intacto")

        with pytest.raises(FileExistsError):
            with storage.open_exclusive(target):
                pass  # pragma: no cover - never entered

        assert target.read_bytes() == b"intacto"

    def test_chunk_reader_round_trips_a_file(self, tmp_path) -> None:
        target = tmp_path / "big.bin"
        payload = b"0123456789" * 1000
        target.write_bytes(payload)

        chunks = list(storage.iter_file_chunks(target, chunk_size=4096))

        assert len(chunks) > 1 and b"".join(chunks) == payload
        assert hashlib.sha256(b"".join(chunks)).digest() == hashlib.sha256(payload).digest()


class TestCopyExclusive:
    def test_copy_is_byte_exact_and_reports_size_and_digest(self, tmp_path) -> None:
        source = tmp_path / "draft.pdf"
        payload = b"%PDF-1.7 contenido " * 200_000
        source.write_bytes(payload)

        result = storage.copy_exclusive(source, tmp_path / "original.pdf")

        assert (tmp_path / "original.pdf").read_bytes() == payload
        assert result.size_bytes == len(payload)
        assert result.sha256 == hashlib.sha256(payload).hexdigest()

    def test_copy_is_an_independent_file_with_mode_0640(self, tmp_path) -> None:
        source = tmp_path / "draft.pdf"
        source.write_bytes(b"datos")

        storage.copy_exclusive(source, tmp_path / "original.pdf")

        copy = tmp_path / "original.pdf"
        assert copy.stat().st_ino != source.stat().st_ino
        assert copy.stat().st_nlink == 1 and mode_of(copy) == 0o640

    def test_copy_never_overwrites_an_existing_file(self, tmp_path) -> None:
        source = tmp_path / "draft.pdf"
        source.write_bytes(b"nuevo")
        destination = tmp_path / "original.pdf"
        destination.write_bytes(b"previo")

        with pytest.raises(FileExistsError):
            storage.copy_exclusive(source, destination)

        assert destination.read_bytes() == b"previo"


class TestPrivateLayout:
    def test_stored_paths_are_relative_to_the_private_volume(self, media_root) -> None:
        user_id, draft_id = uuid4(), uuid4()

        relative = storage.draft_relative_path(user_id, draft_id)

        assert str(relative) == f"drafts/{user_id}/{draft_id}.pdf"
        assert storage.private_path(relative) == media_root / "private" / relative

    def test_version_relative_dir_matches_the_nginx_internal_location(self) -> None:
        manuscript_id = uuid4()

        assert str(storage.version_relative_dir(manuscript_id, 2)) == f"manuscripts/{manuscript_id}/v0002"
