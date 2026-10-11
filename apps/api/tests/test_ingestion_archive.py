import io
import tarfile

import pytest

from app.ingestion.archive import UnsafeArchive, decide_status, inspect_archive
from app.ingestion.limits import IngestionLimits


def archive_bytes(files: dict[str, bytes], *, symlinks: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        directory = tarfile.TarInfo(name="repo-sha")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        for name, content in files.items():
            info = tarfile.TarInfo(name=f"repo-sha/{name}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        for name, target in (symlinks or {}).items():
            info = tarfile.TarInfo(name=f"repo-sha/{name}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            archive.addfile(info)
    return buffer.getvalue()


def test_archive_stores_source_and_skips_dependency_and_symlink() -> None:
    payload = archive_bytes(
        {
            "src/index.ts": b"export const value = 1;\n",
            "node_modules/left-pad/index.js": b"module.exports = 1;\n",
        },
        symlinks={"src/link.ts": "index.ts"},
    )

    inspection = inspect_archive(payload, IngestionLimits())

    by_path = {entry.path: entry for entry in inspection.entries}
    assert by_path["src/index.ts"].disposition == "stored"
    assert by_path["src/index.ts"].content == "export const value = 1;\n"
    assert by_path["node_modules/left-pad/index.js"].reason == "dependency"
    assert by_path["src/link.ts"].reason == "symlink"
    status, error_code, _message = decide_status(inspection.entries)
    assert status == "completed_with_skips"
    assert error_code is None


def test_archive_rejects_path_traversal() -> None:
    payload = archive_bytes({"../../etc/passwd": b"root\n"})

    with pytest.raises(UnsafeArchive):
        inspect_archive(payload, IngestionLimits())


def test_archive_skips_oversized_file_and_binary_content() -> None:
    payload = archive_bytes(
        {
            "src/big.ts": b"a" * 20,
            "src/binary.ts": b"ok\x00no",
            "src/notes.txt": b"plain\n",
        }
    )

    inspection = inspect_archive(payload, IngestionLimits(max_file_bytes=10))
    by_path = {entry.path: entry for entry in inspection.entries}

    assert by_path["src/big.ts"].reason == "file_too_large"
    assert by_path["src/binary.ts"].reason == "binary"
    assert by_path["src/notes.txt"].disposition == "stored"


def test_archive_records_invalid_utf8_as_failed() -> None:
    payload = archive_bytes({"src/broken.ts": b"\xff"})

    inspection = inspect_archive(payload, IngestionLimits())

    assert inspection.entries[0].disposition == "failed"
    assert inspection.entries[0].reason == "not_utf8"
    status, error_code, _message = decide_status(inspection.entries)
    assert status == "failed"
    assert error_code == "partial_failure"


def test_archive_keeps_files_seen_before_a_limit() -> None:
    payload = archive_bytes({"src/a.ts": b"abcd", "src/b.ts": b"efgh"})
    ticks = iter([0, 0, 5])

    inspection = inspect_archive(
        payload,
        IngestionLimits(max_duration_seconds=1),
        now=lambda: next(ticks),
        started_at=0,
    )

    assert inspection.error_code == "limit_exceeded"
    assert inspection.error_message is not None
    assert "time limit" in inspection.error_message
    assert [entry.path for entry in inspection.entries] == ["src/a.ts"]


def test_archive_stops_when_too_many_entries_are_examined() -> None:
    payload = archive_bytes({"src/a.ts": b"a\n", "src/b.ts": b"b\n"})

    inspection = inspect_archive(payload, IngestionLimits(max_entries=1))

    assert inspection.error_code == "limit_exceeded"
    assert [entry.path for entry in inspection.entries] == ["src/a.ts"]


def test_archive_stops_when_stored_text_exceeds_the_total() -> None:
    payload = archive_bytes({"src/a.ts": b"abcd", "src/b.ts": b"efgh"})

    inspection = inspect_archive(payload, IngestionLimits(max_total_bytes=5))

    assert inspection.error_code == "limit_exceeded"
    assert [entry.path for entry in inspection.entries] == ["src/a.ts"]
    assert inspection.entries[0].disposition == "stored"


def test_no_stored_files_is_not_a_complete_snapshot() -> None:
    payload = archive_bytes({"dist/app.js": b"console.log(1)\n"})

    inspection = inspect_archive(payload, IngestionLimits())
    status, error_code, _message = decide_status(inspection.entries)

    assert status == "failed"
    assert error_code == "no_source_files"
