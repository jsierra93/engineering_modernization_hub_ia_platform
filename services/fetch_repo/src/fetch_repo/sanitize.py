"""Tar-slip-safe extraction of an untrusted GitHub tarball.

The tarball is hostile input (CLAUDE.md invariant #9 -- "external content
is untrusted"; in the "solicitud insegura" scenario the repo itself may
be adversarial). A naive `TarFile.extractall()` is a classic path-traversal
/ symlink-escape vulnerability: an entry named e.g. `../../etc/passwd`, an
absolute path, or a symlink pointing outside the extraction root can
overwrite arbitrary files on the machine doing the extracting.

This module never extracts to local disk -- it walks the tar stream in
memory and yields (path, bytes) pairs for members it accepts, skipping (or
raising on) anything unsafe. Callers write the accepted members wherever
they want (here: S3, under `ws/<run_id>/v0/`).
"""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from dataclasses import dataclass

# A few hundred MB of decompressed source is generous for a single repo
# checkout at one commit; anything past this is either not a source repo
# or a zip-bomb-style decompression attack. Chosen as a round, defensible
# number rather than tuned to any real repo.
MAX_TOTAL_UNCOMPRESSED_BYTES = 300 * 1024 * 1024  # 300 MB
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


class TarSanitizationError(Exception):
    """Raised when a tarball contains an entry (or exceeds a limit) that
    makes it unsafe to extract. The caller should treat this as a failed
    fetch, never as a partially-successful one."""


@dataclass(frozen=True)
class SanitizedMember:
    """One accepted regular-file entry, with its path relativized to the
    tar's own top-level directory stripped (GitHub tarballs wrap
    everything in a single `<owner>-<repo>-<sha>/` prefix)."""

    path: str
    data: bytes


def _is_within_root(candidate: str) -> bool:
    """True if a POSIX-normalized relative path never climbs above its
    own root via `..`, and is not absolute."""

    if candidate.startswith("/") or candidate.startswith("\\"):
        return False
    # Reject drive letters (Windows absolute paths) defensively too.
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
    """Strip the single top-level directory GitHub's codeload tarballs
    always add. Returns None for an entry that IS the top-level dir
    itself (nothing to write)."""

    normalized = name.replace("\\", "/").lstrip("/")
    if "/" not in normalized:
        return None
    _, rest = normalized.split("/", 1)
    return rest or None


def iter_sanitized_members(fileobj) -> Iterator[SanitizedMember]:
    """Stream-parse a gzip tarball, yielding only safe regular files.

    Raises `TarSanitizationError` on:
      - absolute paths or `..` path-traversal in the member name
      - symlinks or hardlinks whose target escapes the extraction root
        (a symlink target that stays inside the tree, e.g. a relative
        `./foo.py`, would in principle be fine, but this prototype takes
        the simplest safe stance and rejects ALL symlinks/hardlinks --
        source tarballs from GitHub never legitimately need one)
      - device, FIFO, or other special files
      - a single member, or the cumulative stream, exceeding the size caps

    Never partially extracts: any violation raises before any further
    member is yielded, and callers are expected to discard everything
    written so far for this fetch.
    """

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
