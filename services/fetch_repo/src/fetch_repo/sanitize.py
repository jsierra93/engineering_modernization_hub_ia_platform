"""Tar-slip-safe, in-memory extraction of an untrusted tarball (invariant 9).
Rejects links, devices, path traversal and oversized members.
"""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from dataclasses import dataclass

# Sized to what a 512 MB Lambda survives while holding the tarball, its members and the rebuilt archive.
MAX_TOTAL_UNCOMPRESSED_BYTES = 120 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 20 * 1024 * 1024


class TarSanitizationError(Exception):
    pass


@dataclass(frozen=True)
class SanitizedMember:
    path: str
    data: bytes


def _is_within_root(candidate: str) -> bool:
    if candidate.startswith("/") or candidate.startswith("\\"):
        return False
    if len(candidate) >= 2 and candidate[1] == ":":
        return False

    parts = candidate.replace("\\", "/").split("/")
    depth = 0
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return False
        else:
            depth += 1
    return True


def _strip_top_level(name: str) -> str | None:
    normalized = name.replace("\\", "/").lstrip("/")
    if "/" not in normalized:
        return None
    _, rest = normalized.split("/", 1)
    return rest or None


def iter_sanitized_members(fileobj) -> Iterator[SanitizedMember]:
    total_bytes = 0

    with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
        for member in tar:
            name = member.name

            if member.issym() or member.islnk():
                raise TarSanitizationError(
                    f"rejected tar member {name!r}: symlinks/hardlinks are not allowed"
                )
            if member.isdev():
                raise TarSanitizationError(
                    f"rejected tar member {name!r}: device/FIFO files are not allowed"
                )
            if not (member.isfile() or member.isdir()):
                raise TarSanitizationError(
                    f"rejected tar member {name!r}: unsupported member type"
                )

            if not _is_within_root(name):
                raise TarSanitizationError(
                    f"rejected tar member {name!r}: escapes extraction root"
                )

            if member.isdir():
                continue

            if member.size > MAX_SINGLE_FILE_BYTES:
                raise TarSanitizationError(
                    f"rejected tar member {name!r}: {member.size} bytes exceeds "
                    f"the per-file limit of {MAX_SINGLE_FILE_BYTES}"
                )

            total_bytes += member.size
            if total_bytes > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise TarSanitizationError(
                    "tarball exceeds the total decompressed size limit of "
                    f"{MAX_TOTAL_UNCOMPRESSED_BYTES} bytes"
                )

            relative_path = _strip_top_level(name)
            if relative_path is None:
                continue

            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            data = extracted.read()

            yield SanitizedMember(path=relative_path, data=data)
