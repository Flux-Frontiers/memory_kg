"""CLI and constructor wiring for the ``--vectors`` surface (0.7.0 port).

Coverage after the port showed the renamed surfaces at 30-61%: the commands
declare ``--vectors``, but nothing invoked them, and ``MemoryKG.index`` — the
one real ``SemanticIndex`` construction site — was never reached. That is the
condition under which a bulk rename leaves a latent failure: Click passes
options by keyword, so a decorator renamed to ``--vectors`` against a function
still declaring ``lancedb`` raises ``TypeError`` at call time, and ``--help``
never notices because it renders without running the body.

So these invoke each command and assert the value reaches
``MemoryKG(vectors_path=...)``. The KG is stubbed — nothing here loads a model
or touches a real store.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
from click.testing import CliRunner

from memory_kg.cli.group import cli
from memory_kg.cli.main import cli as main_cli  # noqa: F401 — registers subcommands

# Commands that take --vectors and construct a MemoryKG.
_VECTOR_COMMANDS = ["build", "build-index", "query", "pack", "analyze", "semantic-analyze", "mcp"]


class StubKG:
    """Records constructor kwargs; no model, no store."""

    calls: ClassVar[list[dict]] = []

    def __init__(self, **kwargs):
        StubKG.calls.append(kwargs)

    # -- surface the commands touch --------------------------------------
    def build(self, **_kw):
        return {"indexed_rows": 0}

    def build_graph(self, **_kw):
        return {"nodes": 0}

    def build_index(self, **_kw):
        return {"indexed_rows": 0}

    def query(self, *_a, **_kw):
        return _StubResult()

    def pack(self, *_a, **_kw):
        return _StubPack()

    def close(self):
        pass


class _StubResult:
    hits: ClassVar[list[dict]] = []

    def print_summary(self):
        pass


class _StubPack:
    sections: ClassVar[list[dict]] = []

    def to_markdown(self):
        return "# stub"

    def to_json(self):
        return "{}"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def stub_kg(monkeypatch):
    """Patch the module-level MemoryKG name each command imported."""
    StubKG.calls = []
    for mod in (
        "memory_kg.cli.cmd_query",
        "memory_kg.cli.cmd_build",
        "memory_kg.kg",
        "memory_kg.memorykg_thorough_analysis",
        "memory_kg.memorykg_semantic_analysis",
    ):
        monkeypatch.setattr(f"{mod}.MemoryKG", StubKG, raising=False)
    return StubKG


@pytest.fixture
def corpus(tmp_path):
    """The on-disk artifacts the commands stat before running."""
    dot = tmp_path / ".memorykg"
    dot.mkdir()
    (dot / "graph.sqlite").touch()
    (dot / "vectors.sqlite").touch()
    (tmp_path / "note.md").write_text("# note\n\nbody\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Flag surface
# ---------------------------------------------------------------------------


class TestFlagSurface:
    def _opts(self, name: str) -> set[str]:
        out: set[str] = set()
        for param in cli.commands[name].params:
            out.update(getattr(param, "opts", []))
        return out

    @pytest.mark.parametrize("name", _VECTOR_COMMANDS)
    def test_command_exposes_vectors(self, name):
        assert "--vectors" in self._opts(name)

    @pytest.mark.parametrize("name", sorted(cli.commands))
    def test_no_command_still_offers_lancedb_or_table(self, name):
        opts = self._opts(name)
        assert "--lancedb" not in opts
        assert "--table" not in opts, "--table was LanceDB-only and is removed"

    @pytest.mark.parametrize("name", sorted(cli.commands))
    def test_help_renders(self, runner, name):
        """A rename that breaks a decorator surfaces here as a non-zero exit."""
        result = runner.invoke(cli, [name, "--help"])
        assert result.exit_code == 0, result.output
        assert "lancedb" not in result.output.lower()


# ---------------------------------------------------------------------------
# The value reaches the KG
# ---------------------------------------------------------------------------


class TestVectorsReachesTheKG:
    """`--help` proves the flag parses; only invocation proves it is threaded."""

    def _last_vectors(self, stub_kg) -> Path:
        assert stub_kg.calls, "MemoryKG was never constructed"
        return Path(stub_kg.calls[-1]["vectors_path"])

    def test_query(self, runner, stub_kg, corpus, tmp_path):
        custom = tmp_path / "custom.sqlite"
        result = runner.invoke(
            cli,
            ["query", "hello", "--repo", str(corpus), "--vectors", str(custom)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        assert self._last_vectors(stub_kg) == custom

    def test_pack(self, runner, stub_kg, corpus, tmp_path):
        custom = tmp_path / "custom.sqlite"
        result = runner.invoke(
            cli,
            ["pack", "hello", "--repo", str(corpus), "--vectors", str(custom)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        assert self._last_vectors(stub_kg) == custom

    def test_query_default_is_colocated(self, runner, stub_kg, corpus):
        result = runner.invoke(
            cli, ["query", "hello", "--repo", str(corpus)], catch_exceptions=False
        )
        assert result.exit_code == 0, result.output
        assert self._last_vectors(stub_kg) == corpus / ".memorykg" / "vectors.sqlite"

    def test_default_is_a_file_not_a_directory(self, runner, stub_kg, corpus):
        runner.invoke(cli, ["query", "hello", "--repo", str(corpus)], catch_exceptions=False)
        assert self._last_vectors(stub_kg).name == "vectors.sqlite"
        assert "lancedb" not in str(self._last_vectors(stub_kg))

    def test_no_command_passes_the_removed_table_parameter(self, runner, stub_kg, corpus):
        runner.invoke(cli, ["query", "hello", "--repo", str(corpus)], catch_exceptions=False)
        assert "table" not in stub_kg.calls[-1]
        assert "lancedb_dir" not in stub_kg.calls[-1]


# ---------------------------------------------------------------------------
# The constructor seam
# ---------------------------------------------------------------------------


class TestMemoryKGVectorsPath:
    """`MemoryKG.index` is the only real SemanticIndex construction site."""

    def test_default_is_colocated_with_the_corpus(self, tmp_path):
        from memory_kg.kg import MemoryKG

        kg = MemoryKG(corpus_root=tmp_path)
        assert kg.vectors_path == tmp_path / ".memorykg" / "vectors.sqlite"

    def test_explicit_path_is_honoured(self, tmp_path):
        from memory_kg.kg import MemoryKG

        kg = MemoryKG(corpus_root=tmp_path, vectors_path=tmp_path / "v.sqlite")
        assert kg.vectors_path == tmp_path / "v.sqlite"

    def test_string_paths_are_coerced(self, tmp_path):
        from memory_kg.kg import MemoryKG

        kg = MemoryKG(corpus_root=str(tmp_path), vectors_path=str(tmp_path / "v.sqlite"))
        assert kg.vectors_path == tmp_path / "v.sqlite"

    def test_removed_parameters_are_rejected(self, tmp_path):
        """`lancedb_dir` and `table` are gone — passing them must fail loudly."""
        from memory_kg.kg import MemoryKG

        with pytest.raises(TypeError):
            MemoryKG(corpus_root=tmp_path, lancedb_dir=tmp_path / "lancedb")
        with pytest.raises(TypeError):
            MemoryKG(corpus_root=tmp_path, table="memorykg_nodes")

    def test_index_property_builds_against_vectors_path(self, tmp_path, monkeypatch):
        captured: dict = {}

        class _StubIndex:
            def __init__(self, path, **kw):
                captured["path"] = path
                captured.update(kw)

        monkeypatch.setattr("memory_kg.kg.SemanticIndex", _StubIndex)
        from memory_kg.kg import MemoryKG

        kg = MemoryKG(corpus_root=tmp_path, vectors_path=tmp_path / "v.sqlite")
        monkeypatch.setattr(type(kg), "embedder", property(lambda _self: object()))
        _ = kg.index

        assert captured["path"] == tmp_path / "v.sqlite"
        assert "table" not in captured

    def test_index_property_is_cached(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "memory_kg.kg.SemanticIndex", lambda path, **kw: calls.append(path) or object()
        )
        from memory_kg.kg import MemoryKG

        kg = MemoryKG(corpus_root=tmp_path, vectors_path=tmp_path / "v.sqlite")
        monkeypatch.setattr(type(kg), "embedder", property(lambda _self: object()))
        _, _ = kg.index, kg.index
        assert len(calls) == 1

    def test_repr_names_the_vector_store(self, tmp_path):
        from memory_kg.kg import MemoryKG

        text = repr(MemoryKG(corpus_root=tmp_path))
        assert "vectors_path" in text
        assert "lancedb" not in text.lower()


# ---------------------------------------------------------------------------
# The MCP server's own argparse surface
# ---------------------------------------------------------------------------


class TestMcpServerArgs:
    """mcp_server.py parses its own args — a separate surface from the Click CLI."""

    def _parser_opts(self) -> set[str]:
        import inspect

        import memory_kg.mcp_server as srv

        src = inspect.getsource(srv)
        assert "--vectors" in src
        assert "--lancedb" not in src
        return {"--vectors"}

    def test_declares_vectors_not_lancedb(self):
        assert "--vectors" in self._parser_opts()

    def test_default_points_at_a_file(self):
        import inspect

        import memory_kg.mcp_server as srv

        src = inspect.getsource(srv)
        assert ".memorykg/vectors.sqlite" in src
        assert ".memorykg/lancedb" not in src


# ---------------------------------------------------------------------------
# The analysis entry points
# ---------------------------------------------------------------------------


class TestAnalysisEntryPoints:
    """Both analysis modules take `vectors_path` and default it colocated."""

    @pytest.mark.parametrize(
        "module",
        ["memory_kg.memorykg_thorough_analysis", "memory_kg.memorykg_semantic_analysis"],
    )
    def test_signature_uses_vectors_path(self, module):
        import importlib
        import inspect

        mod = importlib.import_module(module)
        fn = next(
            f
            for _n, f in inspect.getmembers(mod, inspect.isfunction)
            if "vectors_path" in inspect.signature(f).parameters
        )
        params = inspect.signature(fn).parameters
        assert "vectors_path" in params
        assert "lancedb_path" not in params
