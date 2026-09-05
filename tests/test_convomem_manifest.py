"""The ConvoMem loader must refuse to report recall over a partial download.

ConvoMem is the only benchmark here whose corpus is fetched over the network at
run time, and ``discover_files`` returns ``[]`` on *any* exception. A rate limit
or timeout on a category that genuinely exists would otherwise drop it from the
run and shrink the recall denominator, with nothing but a printed warning — and
the output would be indistinguishable from the benign case of a category that
never existed at that tier (tier 3 has no Preferences; tier 4 has only
User/Assistant/Changing Facts).

That failure is not hypothetical in the dangerous direction: tier-1 Preferences
scores 0.960 against a tier mean of 0.963, so silently losing it moves the
published headline *up*.

Network-free throughout — ``discover_files`` and ``download_evidence_file`` are
stubbed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "convomem" / "convomem_bench.py"


def _load_module():
    """Import the benchmark runner by path; it is not a package module."""
    spec = importlib.util.spec_from_file_location("convomem_bench", _BENCH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["convomem_bench"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bench():
    return _load_module()


@pytest.fixture
def stub_fetch(bench, monkeypatch):
    """Stand in for the network, mirroring how the real dataset behaves.

    By default each category serves exactly the count the manifest expects, and
    categories absent from a tier 404 the way upstream does. *missing* forces a
    real category to fail; *per_file* starves every category to simulate a
    truncated download.
    """

    def _install(missing=(), per_file=None):
        def discover(category, cache_dir, tier=1):
            known = bench.TIER_ITEM_COUNTS.get(tier, {})
            if category in missing or category not in known:
                return []
            # One file per item, so a category serves exactly its manifest count
            # (including tier 2's odd 97 Preferences).
            return [f"{category}_{i}.json" for i in range(known[category])]

        def download(category, fpath, cache_dir):
            n = per_file if per_file is not None else 1
            return {"evidence_items": [{"id": f"{fpath}:{i}"} for i in range(n)]}

        monkeypatch.setattr(bench, "discover_files", discover)
        monkeypatch.setattr(bench, "download_evidence_file", download)

    return _install


ALL_CATS = [
    "user_evidence",
    "assistant_facts_evidence",
    "changing_evidence",
    "abstention_evidence",
    "preference_evidence",
    "implicit_connection_evidence",
]


class TestManifest:
    """The manifest must match the published per-tier composition."""

    @pytest.mark.parametrize(("tier", "total"), [(1, 500), (2, 597), (3, 500), (4, 300)])
    def test_tier_totals_match_the_published_results(self, bench, tier, total):
        assert sum(bench.TIER_ITEM_COUNTS[tier].values()) == total

    def test_tier_3_has_no_preferences(self, bench):
        assert "preference_evidence" not in bench.TIER_ITEM_COUNTS[3]

    def test_tier_4_has_only_three_categories(self, bench):
        assert set(bench.TIER_ITEM_COUNTS[4]) == {
            "user_evidence",
            "assistant_facts_evidence",
            "changing_evidence",
        }

    def test_tier_2_preferences_is_the_odd_97(self, bench):
        assert bench.TIER_ITEM_COUNTS[2]["preference_evidence"] == 97


class TestExpectedCounts:
    def test_omits_categories_absent_at_the_tier(self, bench):
        exp = bench.expected_counts(ALL_CATS, 100, tier=4)
        assert set(exp) == {"user_evidence", "assistant_facts_evidence", "changing_evidence"}

    def test_a_smaller_limit_lowers_the_requirement(self, bench):
        assert bench.expected_counts(ALL_CATS, 5, tier=1) == dict.fromkeys(
            bench.TIER_ITEM_COUNTS[1], 5
        )

    def test_limit_never_raises_it_above_the_real_count(self, bench):
        assert bench.expected_counts(ALL_CATS, 10_000, tier=2)["preference_evidence"] == 97


class TestPartialDownloadIsRefused:
    def test_a_fetch_failure_on_a_real_category_raises(self, bench, stub_fetch):
        stub_fetch(missing=["preference_evidence"])
        with pytest.raises(RuntimeError, match="fetch failure"):
            bench.load_evidence_items(ALL_CATS, 100, "/tmp/x", tier=1)

    def test_the_error_names_the_category(self, bench, stub_fetch):
        stub_fetch(missing=["abstention_evidence"])
        with pytest.raises(RuntimeError, match="abstention_evidence"):
            bench.load_evidence_items(ALL_CATS, 100, "/tmp/x", tier=1)

    def test_short_counts_raise_even_when_files_listed(self, bench, stub_fetch):
        """A truncated download lists files but yields too few items."""
        stub_fetch(per_file=0)
        with pytest.raises(RuntimeError, match="do not match the manifest"):
            bench.load_evidence_items(ALL_CATS, 100, "/tmp/x", tier=1)

    def test_an_unexpected_category_also_raises(self, bench, stub_fetch, monkeypatch):
        """The mirror failure: an extra category grows the denominator."""
        stub_fetch()
        monkeypatch.setitem(bench.TIER_ITEM_COUNTS, 4, dict(bench.TIER_ITEM_COUNTS[4]))
        real_discover = bench.discover_files
        monkeypatch.setattr(
            bench,
            "discover_files",
            lambda c, d, tier=1: (
                [f"{c}_0.json"] if c == "preference_evidence" else real_discover(c, d, tier=tier)
            ),
        )
        with pytest.raises(RuntimeError, match="preference_evidence"):
            bench.load_evidence_items(ALL_CATS, 100, "/tmp/x", tier=4)

    def test_a_category_absent_at_this_tier_is_not_an_error(self, bench, stub_fetch):
        """Tier 4 legitimately lacks three categories; upstream 404s on them."""
        stub_fetch()
        items = bench.load_evidence_items(ALL_CATS, 100, "/tmp/x", tier=4)
        assert len(items) == 300

    def test_a_complete_tier_1_load_passes(self, bench, stub_fetch):
        stub_fetch()
        assert len(bench.load_evidence_items(ALL_CATS, 100, "/tmp/x", tier=1)) == 500

    def test_a_complete_tier_2_load_passes_with_the_97(self, bench, stub_fetch):
        stub_fetch()
        assert len(bench.load_evidence_items(ALL_CATS, 100, "/tmp/x", tier=2)) == 597
