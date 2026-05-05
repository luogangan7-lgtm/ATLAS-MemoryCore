# Changelog

All notable changes to ATLAS-MemoryCore are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v0.1.0] — 2026-05-05

First public release. Marks the point where the OpenClaw plugin is
stable enough for daily use and the repository is cleaned up to reflect
actual capabilities.

### Added

- **`openclaw-plugin/index.js`** — Production OpenClaw plugin (v10.0):
  - Four-tier knowledge maturity model: L0 raw → L1 structured → L2 insight → L3 framework
  - Hierarchical injection: searches L3→L2→L1→L0, injects the most mature context first
  - `L1CompletionAgent`: background agent that monitors L0 nodes and promotes them to L1
  - `atlas_feedback` tool: correct/wrong/outdated ratings; negative ratings suppress injection
  - `atlas_distill`: synthesizes multiple memories into a distilled principle via DeepSeek
  - `atlas_timeline`: retrieves all memories for a tag, sorted by time
  - `atlas_evolve`: manual trigger for dedup + expiry cleanup + auto-distill
  - Obsidian Bridge: exports to `L1/<domain>/`, `L2/`, `L3/` with Dataview-ready frontmatter
  - LRU embedding cache (200 entries) with 2.5 s timeout guard on every INJECT call
  - Version chain: superseded memories kept with `status: superseded`, not deleted

- **`scripts/course_to_l1_pipeline.py`** — Batch L1 knowledge extraction:
  - Reads `.txt` course transcripts, optionally guided by an `.xmind` skeleton
  - Calls DeepSeek v4-flash (1 M context, 384 K output) to produce structured knowledge docs
  - Format: `#### N.N [title]` → **核心内容** / **如何运用** / **关联知识** / verbatim quote block
  - Writes to local `核心知识整理/`, Obsidian `L1/<domain>/`, and Qdrant `atlas_memories`
  - `--group 1 / --group 2` splits course list for parallel execution without OOM

- **`benchmark/retrieval_comparison.py`** — Real retrieval benchmark:
  - 10 hand-labeled memories, 6 queries with ground truth
  - Compares: keyword match vs vanilla vector search vs time-decay reranking
  - Reports measured P@3, R@3, and actual latency (no simulated `time.sleep`)

### Changed

- **`openclaw-plugin/index.js`**: upgraded from v9.5 to v10. Embedding model
  changed from `nomic-embed-text` (768-dim) to `bge-m3` (1024-dim);
  Qdrant collection must be rebuilt when upgrading.

- **`src/core/turboquant_compressor.py`**: removed the false attribution to
  "Google Research 2026". The module implements standard group-wise 4-bit
  quantization (group_size=128, per-group scale + zero-point). It reduces
  vector storage by ~75% but does not affect LLM token consumption.

- **`docs/AEGIS_CORTEX_V6.2.md`**: performance table now explicitly marks
  all numbers as coming from synthetic tests; adds disclaimer.

### Removed

- Auto-generated status report files: `PHASE2_COMPLETION.md`,
  `PHASE3_COMPLETION.md`, `FINAL_PRODUCTION_REPORT.md`,
  `PRODUCTION_DEPLOYMENT_REPORT.md`, `PROJECT_COMPLETION.md`,
  `PROJECT_STATUS_V6.2.md`, `DEVELOPMENT_STATUS.md`, `README_V6.md`,
  `PROJECT_SUMMARY.md`. These were generated during development and
  contained fabricated timestamps, inflated metrics, and no useful
  information for users.

- All root-level test/verify scripts moved to `tests/` and `scripts/`.

### Known Limitations

- The `src/` Python package (AEGIS-Cortex v6.2 architecture) is experimental
  and not integrated with the OpenClaw plugin. Treat it as a separate research
  branch.
- The `benchmark/benchmark_v6_vs_v6.2.py` file is kept for history but is
  entirely simulated and should not be cited as performance evidence.
- `retrieval_comparison.py` uses a 10-entry test set. Results are directional,
  not statistically significant.

---

## [Pre-release] — 2026-04-21 to 2026-05-04

Rapid iteration during initial development. Changes were not logged individually.
See git history for details.
