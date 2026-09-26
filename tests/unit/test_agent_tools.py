"""Task 3.3: tools are directly callable (Strands' @tool decorator keeps
the underlying function reachable), so these are plain unit tests -- no
Agent, no Bedrock, matching PLAN.md 3.3's "sin Bedrock" scope."""

from __future__ import annotations

from agent_phase.tools import build_tools


class _DictWorkspace:
    def __init__(self):
        self.files: dict[str, str] = {}

    def read(self, path):
        return self.files[path]

    def write(self, path, content):
        self.files[path] = content

    def list(self, prefix=""):
        return [p for p in self.files if p.startswith(prefix)]


def test_read_file_wraps_content_as_untrusted():
    ws = _DictWorkspace()
    ws.files["src/a.py"] = "import os"
    read_file, list_files, write_file, fetch_doc = build_tools(ws, fetch_doc_fn=lambda url: "unused")

    result = read_file("src/a.py")

    assert result.startswith('<untrusted source="repo:src/a.py">')
    assert "import os" in result
    assert result.rstrip().endswith("</untrusted>")


def test_write_file_actually_writes_through_to_workspace():
    ws = _DictWorkspace()
    read_file, list_files, write_file, fetch_doc = build_tools(ws, fetch_doc_fn=lambda url: "unused")

    write_file("src/b.py", "x = 1")

    assert ws.files["src/b.py"] == "x = 1"


def test_list_files_returns_bare_paths_no_wrapping():
    ws = _DictWorkspace()
    ws.files["a.py"] = "..."
    ws.files["b.py"] = "..."
    read_file, list_files, write_file, fetch_doc = build_tools(ws, fetch_doc_fn=lambda url: "unused")

    assert set(list_files()) == {"a.py", "b.py"}


def test_fetch_doc_tool_wraps_content_and_delegates_to_injected_fetcher():
    ws = _DictWorkspace()
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return "pydantic v2 migration guide content"

    read_file, list_files, write_file, fetch_doc = build_tools(ws, fetch_doc_fn=fake_fetch)

    result = fetch_doc("https://docs.pydantic.dev/latest/migration/")

    assert calls == ["https://docs.pydantic.dev/latest/migration/"]
    assert result.startswith('<untrusted source="doc:https://docs.pydantic.dev/latest/migration/">')
    assert "pydantic v2 migration guide content" in result


def test_fetch_doc_tool_surfaces_rejection_as_a_tool_error_not_a_crash():
    ws = _DictWorkspace()

    def rejecting_fetch(url):
        raise ValueError("host not on the allowlist")

    read_file, list_files, write_file, fetch_doc = build_tools(ws, fetch_doc_fn=rejecting_fetch)

    result = fetch_doc("https://evil.example.com/x")

    assert "error" in result.lower()
    assert "not on the allowlist" in result


def test_read_file_on_missing_path_is_a_tool_error_not_a_crash():
    ws = _DictWorkspace()
    read_file, list_files, write_file, fetch_doc = build_tools(ws, fetch_doc_fn=lambda url: "unused")

    result = read_file("does/not/exist.py")

    assert "error" in result.lower()
