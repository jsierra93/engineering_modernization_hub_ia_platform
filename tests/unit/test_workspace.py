"""Task 3.3/3.5 support: workspace path-scoping is what the policy gate's
write check assumes is already safe at the storage layer -- both layers
matter (defense in depth), so both get their own tests."""

from __future__ import annotations

import pytest

from agent_phase.workspace import S3Workspace, WorkspacePathError


class _FakeBucket:
    """Minimal stand-in for a boto3 Bucket resource -- an in-memory dict
    is enough to prove S3Workspace's prefix-scoping logic; moto/real S3
    correctness is proven elsewhere (fetch_repo's own tests)."""

    def __init__(self):
        self.objects_store: dict[str, bytes] = {}

    def Object(self, key):
        store = self.objects_store

        class _Obj:
            def get(self_inner):
                if key not in store:
                    raise KeyError(key)
                return {"Body": _Body(store[key])}

        return _Obj()

    def put_object(self, Key, Body):
        self.objects_store[Key] = Body if isinstance(Body, bytes) else Body.encode()

    @property
    def objects(self):
        store = self.objects_store

        class _Objects:
            def filter(self_inner, Prefix):
                class _Key:
                    def __init__(self, key):
                        self.key = key

                return [_Key(k) for k in store if k.startswith(Prefix)]

        return _Objects()


class _Body:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class _FakeS3Resource:
    def __init__(self, bucket: _FakeBucket):
        self._bucket = bucket

    def Bucket(self, name):
        return self._bucket


@pytest.fixture()
def workspace():
    bucket = _FakeBucket()
    return S3Workspace(_FakeS3Resource(bucket), bucket="modhub-workspaces", run_id="run-1")


def test_write_then_read_round_trips(workspace):
    workspace.write("src/models.py", "print('hi')")
    assert workspace.read("src/models.py") == "print('hi')"


def test_list_returns_paths_relative_to_the_run_prefix(workspace):
    workspace.write("pyproject.toml", "[project]")
    workspace.write("src/a.py", "x = 1")
    assert set(workspace.list()) == {"pyproject.toml", "src/a.py"}


def test_path_traversal_is_rejected_on_read():
    bucket = _FakeBucket()
    ws = S3Workspace(_FakeS3Resource(bucket), bucket="modhub-workspaces", run_id="run-1")
    with pytest.raises(WorkspacePathError):
        ws.read("../../etc/passwd")


def test_path_traversal_is_rejected_on_write():
    bucket = _FakeBucket()
    ws = S3Workspace(_FakeS3Resource(bucket), bucket="modhub-workspaces", run_id="run-1")
    with pytest.raises(WorkspacePathError):
        ws.write("../outside.py", "evil")


def test_absolute_path_is_rejected():
    bucket = _FakeBucket()
    ws = S3Workspace(_FakeS3Resource(bucket), bucket="modhub-workspaces", run_id="run-1")
    with pytest.raises(WorkspacePathError):
        ws.write("/etc/passwd", "evil")


def test_two_runs_never_share_a_prefix():
    bucket = _FakeBucket()
    ws1 = S3Workspace(_FakeS3Resource(bucket), bucket="modhub-workspaces", run_id="run-1")
    ws2 = S3Workspace(_FakeS3Resource(bucket), bucket="modhub-workspaces", run_id="run-2")
    ws1.write("a.py", "run1 content")
    ws2.write("a.py", "run2 content")
    assert ws1.read("a.py") == "run1 content"
    assert ws2.read("a.py") == "run2 content"
