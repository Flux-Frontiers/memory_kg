"""Pin ``benchmarks/`` to the live ``MemoryKG`` / ``SemanticIndex`` API.

The benchmark runners are not imported by the package and not exercised by any
other test, so they drift silently — and the drift only surfaces on a
multi-hour eval run against a downloaded corpus. The sqlite-vec port broke all
five of them at once in two different ways, both caught here:

* ``MemoryKG(lancedb_dir=...)`` became a ``TypeError`` when the parameter was
  renamed to ``vectors_path``.
* ``vectors_path.mkdir(...)`` was correct while the vector store was a LanceDB
  *directory* and fatal once it became a sqlite-vec *file* — the runner created
  a directory where the backend then tried to open a database, and
  ``sqlite3.connect`` failed with ``unable to open database file`` only after
  the (slow) graph phase had already completed.

These are static checks on purpose: they run in milliseconds, need no corpus,
no model and no network, and they fail on the call site rather than on the
symptom several hundred seconds downstream.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from memory_kg.index import SemanticIndex
from memory_kg.kg import MemoryKG

BENCH_DIR = Path(__file__).resolve().parent.parent / "benchmarks"

#: Every runner that constructs a MemoryKG or a SemanticIndex.
RUNNERS = (
    "build_dockg.py",
    "convomem/convomem_bench.py",
    "locomobench/locomo_bench_memkg.py",
    "longmemeval/longmemeval_memkg.py",
    "membench/membench_bench.py",
)

#: Constructors whose keyword arguments are checked against the real signature.
#: ``test_similar.py`` is deliberately absent — it drives DocKG's SemanticIndex,
#: a different class with a different (still directory-based) parameter name.
CHECKED = {
    "MemoryKG": MemoryKG,
    "SemanticIndex": SemanticIndex,
}


def _sources() -> list[tuple[str, ast.Module]]:
    out = []
    for rel in RUNNERS:
        path = BENCH_DIR / rel
        assert path.is_file(), f"benchmark runner went missing: {rel}"
        out.append((rel, ast.parse(path.read_text(), filename=str(path))))
    return out


SOURCES = _sources()


def _accepted(cls: type) -> set[str]:
    return {
        n
        for n, p in inspect.signature(cls.__init__).parameters.items()
        if n != "self" and p.kind is not p.VAR_KEYWORD
    }


def _calls(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name:
            yield node


@pytest.mark.parametrize("rel,tree", SOURCES, ids=[r for r, _ in SOURCES])
class TestConstructorKeywords:
    """Renaming a parameter must not leave a runner calling the old name."""

    @pytest.mark.parametrize("ctor", sorted(CHECKED))
    def test_keywords_are_accepted(self, rel, tree, ctor):
        accepted = _accepted(CHECKED[ctor])
        for call in _calls(tree, ctor):
            for kw in call.keywords:
                if kw.arg is None:  # **kwargs splat — nothing static to check
                    continue
                assert kw.arg in accepted, (
                    f"{rel}:{call.lineno} passes {ctor}({kw.arg}=...), "
                    f"which {ctor}.__init__ does not accept. Accepted: {sorted(accepted)}"
                )

    def test_positional_args_are_within_arity(self, rel, tree):
        """A dropped positional (``table``) would otherwise land silently."""
        for ctor, cls in CHECKED.items():
            params = inspect.signature(cls.__init__).parameters
            n_positional = sum(
                1 for n, p in params.items() if n != "self" and p.kind is p.POSITIONAL_OR_KEYWORD
            )
            for call in _calls(tree, ctor):
                n_given = sum(1 for a in call.args if not isinstance(a, ast.Starred))
                assert n_given <= n_positional, (
                    f"{rel}:{call.lineno} passes {n_given} positional args to {ctor}, "
                    f"which takes at most {n_positional}"
                )


@pytest.mark.parametrize("rel,tree", SOURCES, ids=[r for r, _ in SOURCES])
class TestVectorStoreIsAFile:
    """``vectors.sqlite`` is a file. Creating it as a directory breaks the open."""

    def test_no_mkdir_on_the_vectors_path_itself(self, rel, tree):
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "mkdir":
                continue
            target = node.func.value
            # `vectors_path.mkdir(...)` — wrong. `vectors_path.parent.mkdir(...)`
            # — right, and reaches here as an Attribute, not a Name.
            if isinstance(target, ast.Name) and "vector" in target.id.lower():
                pytest.fail(
                    f"{rel}:{node.lineno} calls {target.id}.mkdir(...). The vector store is a "
                    f"sqlite-vec file, not a LanceDB directory — use {target.id}.parent.mkdir(...)."
                )


@pytest.mark.parametrize("rel,tree", SOURCES, ids=[r for r, _ in SOURCES])
class TestNoLanceDBResidue:
    """The port is only finished when nothing reaches for the old backend."""

    def test_does_not_import_lancedb(self, rel, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(n.split(".")[0] == "lancedb" for n in names), (
                f"{rel}:{node.lineno} still imports lancedb"
            )

    def test_no_lancedb_identifiers(self, rel, tree):
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.keyword):
                name = node.arg
            if name and "lancedb" in name.lower():
                pytest.fail(f"{rel}:{node.lineno} still references `{name}`")


class TestSourceLevelResidue:
    """Strings and CLI flags are invisible to the AST checks above."""

    @pytest.mark.parametrize("rel", RUNNERS)
    def test_no_lancedb_in_flags_or_env_vars(self, rel):
        text = (BENCH_DIR / rel).read_text()
        for token in ("--lancedb", "DOCKG_LANCEDB", "MEMORYKG_LANCEDB"):
            assert token not in text, f"{rel} still uses `{token}`"
