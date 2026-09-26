"""Task 2.2: mocked HTTP download (via `responses`) + moto S3 confirm a
clean tarball lands correctly under `ws/<run_id>/v0/`, and a tarball with
a path-traversal or symlink-escape entry is rejected rather than silently
extracted.
"""

from __future__ import annotations

import io
import tarfile

import boto3
import pytest
import requests
import responses
from moto import mock_aws

from fetch_repo.handler import HttpGetError, fetch_and_store_repo
from fetch_repo.sanitize import TarSanitizationError

REPO = "example/demo"
COMMIT = "a" * 40
BUCKET = "modhub-workspaces"
TAR_URL = f"https://codeload.github.com/{REPO}/tar.gz/{COMMIT}"
TOP_LEVEL = f"example-demo-{COMMIT[:7]}"


def _build_tar_gz(entries: dict[str, bytes], extra_members=None) -> bytes:
    """Build an in-memory .tar.gz with the given {path: content} entries,
    each wrapped under the same top-level dir GitHub tarballs use.
    `extra_members` lets a test append raw TarInfo entries (e.g. a
    symlink) not expressible as a simple path/content pair."""

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, content in entries.items():
            info = tarfile.TarInfo(name=f"{TOP_LEVEL}/{path}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        for info, content in (extra_members or []):
            if content is not None:
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            else:
                tar.addfile(info)
    return buf.getvalue()


@pytest.fixture()
def s3_resource():
    with mock_aws():
        resource = boto3.resource("s3", region_name="us-east-1")
        resource.create_bucket(Bucket=BUCKET)
        yield resource


def test_clean_tarball_lands_under_ws_run_id_v0(s3_resource):
    run_id = "11111111-1111-1111-1111-111111111111"
    tar_bytes = _build_tar_gz(
        {
            "pyproject.toml": b"[project]\nname = 'demo'\n",
            "src/demo/__init__.py": b"",
            "src/demo/main.py": b"print('hello')\n",
        }
    )

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, TAR_URL, body=tar_bytes, status=200)
        result = fetch_and_store_repo(
            run_id=run_id,
            repo=REPO,
            commit=COMMIT,
            bucket=BUCKET,
            http_session=requests.Session(),
            s3_resource=s3_resource,
        )

    assert result.prefix == f"ws/{run_id}/v0/"
    assert set(result.object_keys) == {
        f"ws/{run_id}/v0/pyproject.toml",
        f"ws/{run_id}/v0/src/demo/__init__.py",
        f"ws/{run_id}/v0/src/demo/main.py",
    }

    obj = s3_resource.Object(BUCKET, f"ws/{run_id}/v0/src/demo/main.py")
    assert obj.get()["Body"].read() == b"print('hello')\n"


def test_path_traversal_entry_is_rejected(s3_resource):
    run_id = "22222222-2222-2222-2222-222222222222"
    tar_bytes = _build_tar_gz(
        {
            "pyproject.toml": b"[project]\n",
            "../../etc/evil.txt": b"pwned",
        }
    )

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, TAR_URL, body=tar_bytes, status=200)
        with pytest.raises(TarSanitizationError):
            fetch_and_store_repo(
                run_id=run_id,
                repo=REPO,
                commit=COMMIT,
                bucket=BUCKET,
                http_session=requests.Session(),
                s3_resource=s3_resource,
            )

    # Nothing from this malicious tarball should be trusted/present.
    listed = list(s3_resource.Bucket(BUCKET).objects.filter(Prefix=f"ws/{run_id}/"))
    assert listed == [] or all("evil" not in o.key for o in listed)


def test_symlink_escape_entry_is_rejected(s3_resource):
    run_id = "33333333-3333-3333-3333-333333333333"
    symlink_info = tarfile.TarInfo(name=f"{TOP_LEVEL}/escape_link")
    symlink_info.type = tarfile.SYMTYPE
    symlink_info.linkname = "../../../../etc/passwd"

    tar_bytes = _build_tar_gz(
        {"pyproject.toml": b"[project]\n"},
        extra_members=[(symlink_info, None)],
    )

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, TAR_URL, body=tar_bytes, status=200)
        with pytest.raises(TarSanitizationError):
            fetch_and_store_repo(
                run_id=run_id,
                repo=REPO,
                commit=COMMIT,
                bucket=BUCKET,
                http_session=requests.Session(),
                s3_resource=s3_resource,
            )


def test_absolute_path_entry_is_rejected(s3_resource):
    run_id = "44444444-4444-4444-4444-444444444444"
    abs_info = tarfile.TarInfo(name="/etc/evil.txt")
    content = b"pwned"

    tar_bytes = _build_tar_gz(
        {"pyproject.toml": b"[project]\n"},
        extra_members=[(abs_info, content)],
    )

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, TAR_URL, body=tar_bytes, status=200)
        with pytest.raises(TarSanitizationError):
            fetch_and_store_repo(
                run_id=run_id,
                repo=REPO,
                commit=COMMIT,
                bucket=BUCKET,
                http_session=requests.Session(),
                s3_resource=s3_resource,
            )


def test_http_failure_raises_http_get_error(s3_resource):
    run_id = "55555555-5555-5555-5555-555555555555"

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, TAR_URL, status=404)
        with pytest.raises(HttpGetError):
            fetch_and_store_repo(
                run_id=run_id,
                repo=REPO,
                commit=COMMIT,
                bucket=BUCKET,
                http_session=requests.Session(),
                s3_resource=s3_resource,
            )
