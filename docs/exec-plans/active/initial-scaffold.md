# Execution Plan: Initial Scaffold

Status: ACTIVE
Opened: 2026-03-28
Owner: human (pending decisions) / agent (pending approval)

---

## Decision Stub 1: Which models to benchmark first? ✓ RESOLVED

**Question:** What is the initial model set for benchmarking?

**Options:**
- ResNet50 — stable baseline, well-understood, good for sanity-checking harness correctness
- YOLOv8 — common AV/robotics model, good real-world relevance for embedded GPU target
- A transformer (e.g. BERT-base or ViT-B/16) — stresses memory bandwidth, relevant for
  multimodal pipelines

**Tradeoffs:**
- ResNet50: easiest to get running across all runtimes; low signal for AV workloads
- YOLOv8: high relevance to target use-case; ONNX export path well-supported in TRT
- Transformer: highest memory pressure; may expose runtime differences most clearly;
  harder to get consistent calibration data for INT8

**Decision:** ResNet50 first. Focus is vision models for robotics; DINOv2 is next after
the pipeline is proven end-to-end. Language models are out of scope.
**Date resolved:** 2026-03-28

---

## Decision Stub 2: Target hardware priority ✓ RESOLVED

**Question:** Should Jetson AGX Orin be the sole target initially, or should Thor be
scoped from the start?

**Options:**
- Orin-only first — simpler; Thor SDK is less mature; focus on harness correctness
- Orin + Thor from day 1 — forces multi-hardware abstraction early; avoids retrofit later

**Tradeoffs:**
- Orin-only: faster to first valid result; risk of Orin-specific assumptions baking in
- Orin + Thor: higher upfront complexity; hw_id abstraction is cleaner from the start

**Decision:** Thor only. Orin is out of scope for now.
**Date resolved:** 2026-03-28

---

## Decision Stub 3: Website hosting ✓ RESOLVED

**Question:** Static GitHub Pages or dynamic hosting?

**Options:**
- GitHub Pages (static) — zero ops; free; fits "boring tech" principle; no server to maintain
- Dynamic (e.g. Vercel, self-hosted) — server-side filtering/sorting; richer UX possible

**Tradeoffs:**
- Static: simpler CI pipeline; all filtering must be client-side JS or pre-generated;
  large result sets may inflate repo size
- Dynamic: more operational complexity; overkill for daily-updated benchmark table

**Decision:** GitHub Pages. Keep it simple.
**Date resolved:** 2026-03-28

---

## Decision Stub 4: Results storage backend ✓ RESOLVED

**Question:** Flat JSON in repo or external DB?

**Options:**
- Flat JSON in results/ (in-repo) — repo is the single source of truth; trivially diffable;
  git history is the audit log; fits "legibility" principle
- External DB (e.g. SQLite sidecar, ClickHouse, Supabase) — query-friendly; scales better
  for large result sets; decouples storage from version control

**Tradeoffs:**
- Flat JSON: simple; self-contained; git blame works; large history may slow clone
- External DB: enables richer queries; breaks "repo is system of record" invariant;
  requires extra infra and credentials management

**Decision:** Flat JSON in results/. Repo is the source of truth.
**Date resolved:** 2026-03-28
