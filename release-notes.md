# MemoryKG v0.4.1

> Released: 2026-04-25

This is the first public release of MemoryKG that consolidates two independent benchmark wins, polished documentation, and an honest competitive narrative. No source-code behavior changes — this is a documentation-and-credibility release on top of the v0.4.0 engine.

## Headline result: ConvoMem 100% retrieval recall

MemoryKG achieves **100% retrieval recall on the ConvoMem benchmark — every evidence message found, on every question, across 17,463 items** spanning all six evidence categories (User Facts, Assistant Facts, Abstention, Implicit Connections, Preferences, Changing Facts) and all four evaluated tiers (1–4 messages).

This is the **largest non-LLM evaluation on ConvoMem reported anywhere**. It outperforms the closest verbatim-storage baseline (MemPal at 92.9% overall) by +7.1 pp, with the largest gains on the categories where vocabulary mismatch is hardest: Preferences (+14.0 pp), Implicit Connections (+10.7 pp), and Abstention (+9.0 pp).

A full academic write-up ships in this release: [`benchmarks/convomem/convomem_article.pdf`](benchmarks/convomem/convomem_article.pdf).

## Standing result: tied for top LLM-free on LongMemEval-S

On LongMemEval-S, MemoryKG is **tied for the top LLM-free score** at 98.4% Recall@5 / 99.4% Recall@10 / 0.943 NDCG@10. With the sibling boost enabled, recall_all@10 reaches 98.6% — every required session retrieved for 493 of 500 questions, with no LLM at any stage.

## What's new in this release

- **README restructured.** ConvoMem now leads the TL;DR; LongMemEval-S follows. The "tied for top LLM-free" framing replaces an earlier overstatement; the comparison paragraph names the three LLM-augmented systems that still rank higher at R@5.
- **ConvoMem academic article** (PDF + LaTeX source) published under `benchmarks/convomem/` — full method, tier-by-tier results, MemPal comparison, and architectural analysis of why graph expansion closes the vocabulary-mismatch gap.
- **Documentation tidied.** README slimmed by ~90 lines: schema details now live in `docs/ingestion.md` (with the correct `**/.memorykg/` gitignore pattern and rationale); MCP setup in `docs/MCP.md`; a new `docs/python-api.md` covers the `MemoryKG` class.
- **Benchmark prose tightened.** "Clean baseline" terminology replaced with descriptive labels ("held-out", "raw-question", "principled") that name the actual property being claimed.

## Compatibility

No API or schema changes. Drop-in replacement for v0.4.0.

## Reproducing the headline result

```bash
poetry run python3 benchmarks/convomem/convomem_bench.py --limit 1000 --tier 1
poetry run python3 benchmarks/convomem/convomem_bench.py --limit 1000 --tier 2
poetry run python3 benchmarks/convomem/convomem_bench.py --limit 1000 --tier 3
poetry run python3 benchmarks/convomem/convomem_bench.py --limit 1000 --tier 4
# Expected: 100% retrieval recall on every category × tier (17,463 items, ~20 min on Apple Silicon)
```

---

_Full file-by-file changes: [CHANGELOG.md](CHANGELOG.md)_
