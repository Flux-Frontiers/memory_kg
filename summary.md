# Agentic Search vs. the KG Stack — Work Summary

This branch (`claude/agentic-search-analysis-ac9h6m`) responds to Abdullah Grewal's
*"AI Agents Don't Need Vector Search Anymore: Inside the Agentic Search Stack Replacing
RAG in 2026."* It evaluates the article's claims against the Flux-Frontiers KG stack
(**PyCodeKG**, **MemoryKG**, **DocKG**), adds three new benchmarks, and reports the
results — including the negative and self-corrected ones.

## Headline finding — structural expansion is *regime-specific*

We ran the article's flat-vs-graph head-to-head (`--hop 0` vs `--hop 1`) five ways. The
result is a map, not a slogan:

| benchmark / regime | does graph expansion help? |
|---|---|
| HotpotQA (dense passage QA) | **hurts** (−0.09 recall_all@5) |
| SWE-bench single-file, file-level | null (Δ 0.000) |
| SWE-bench single-file, symbol-level | ~null (+0.006 MRR) |
| SWE-bench multi-file, file-level | null (Δ 0.000) |
| **SWE-bench multi-file, symbol-level** | **helps (+0.21 sym-recall@20)** |

**Takeaways:** (1) flat, precomputed, deterministic retrieval is already competitive
($0/query, reproducible) — the axes where agentic `grep` admits it loses; (2) graph
expansion is **not** a universal reranker — four of five regimes show null or harm; but
(3) it **measurably recovers cross-file targets similarity misses** in the one regime
built for it (multi-file symbol localization), confirming the article's own
"similarity ≠ structural relevance" with a sign and magnitude. All numbers are
small-n pilots (n = 13–100); label as such if published.

---

## Documents

### Analysis & write-ups
- **[analysis/agentic_search_2026_analysis.md](analysis/agentic_search_2026_analysis.md)**
  — full claim-by-claim analysis of the article against the KG stack, with the regime
  map and the capability evidence. The main analytical document.
- **[announcements/REBUTTAL_agents_still_need_structure.md](announcements/REBUTTAL_agents_still_need_structure.md)**
  — the publishable rebuttal article: *"Your Agent Doesn't Need Vector Search. It Needs
  Structure."* Concedes the article's valid points, reframes precompute↔JIT, and carries
  the honest results (including where the graph lost).
- **[analysis/pycodekg_call_resolution_finding.md](analysis/pycodekg_call_resolution_finding.md)**
  — issue-ready bug finding for `pycode_kg`: name-based call resolution over-approximates
  `callers`/fan-in/centrality for shared method names (`get` etc.), because consumers
  ignore the confidence PyCodeKG already computes. Ranked fixes + reproduction +
  acceptance test. *(Self-contained; intended to be moved into `pycode_kg`.)*

### Benchmark: HotpotQA (multi-hop document QA)
- **[benchmarks/hotpotqa/README.md](benchmarks/hotpotqa/README.md)** — what it tests and why.
- **[benchmarks/hotpotqa/hotpotqa_bench.py](benchmarks/hotpotqa/hotpotqa_bench.py)** — harness
  (HF-parquet fallback download, LLM-free `recall_all@N`, `--hop` head-to-head).
- Results: [hop 0](benchmarks/hotpotqa/results_hotpot_top10_hop0_sample100.json) ·
  [hop 1](benchmarks/hotpotqa/results_hotpot_top10_hop1_sample100.json) (n=100).
  *Finding: graph expansion hurts on dense haystacks (0.70 → 0.61 recall_all@5).*

### Benchmark: SWE-bench (code localization, PyCodeKG)
- **[benchmarks/swebench/README.md](benchmarks/swebench/README.md)** — task, metrics, and the
  full regime map.
- **[benchmarks/swebench/swebench_pycodekg.py](benchmarks/swebench/swebench_pycodekg.py)** —
  harness: file- and symbol-level localization, build-once/query-both-hops,
  `--min-gold-files` multi-file filter, Lite/Verified.
- Results:
  [Lite single-file](benchmarks/swebench/results_swebench_lite_hop0-1_light.json) ·
  [Lite symbol-level](benchmarks/swebench/results_swebench_lite_symbol_hop0-1.json) ·
  [**Verified multi-file**](benchmarks/swebench/results_swebench_verified_multifile_hop0-1.json) (the positive result) ·
  [flask end-to-end](benchmarks/swebench/results_swebench_lite_hop1_flask4045.json).

### Benchmark: Capabilities (structural queries embeddings/grep can't do)
- **[benchmarks/capabilities/README.md](benchmarks/capabilities/README.md)** — the
  capability table (callers / fan-in / dead code).
- **[benchmarks/capabilities/capability_demo.py](benchmarks/capabilities/capability_demo.py)** —
  runs PyCodeKG over any repo; reports fan-in hotspots, dead code, and a callers-vs-grep
  head-to-head (flags name-collision over-approximation honestly).
- Example report on `psf/requests`:
  [Markdown](benchmarks/capabilities/REPORT_psf__requests.md) ·
  [JSON](benchmarks/capabilities/REPORT_psf__requests.json).
  *Finding: "who calls `httpbin`" → 45 exact caller functions vs 98 raw grep hits.*

---

## How to reproduce

```bash
pip install pycode-kg                 # for the SWE-bench + capability benchmarks
export PYCODEKG_DEVICE=cpu DOCKG_DEVICE=cpu

python benchmarks/hotpotqa/hotpotqa_bench.py --limit 100 --hop 0   # and --hop 1
python benchmarks/swebench/swebench_pycodekg.py --dataset lite --hop 0,1
python benchmarks/swebench/swebench_pycodekg.py --dataset verified --min-gold-files 2 --hop 0,1
python benchmarks/capabilities/capability_demo.py --repo /path/to/python/repo
```
