# Plan: add-cosmos-reason-2b
Status: completed (superseded)

---

## Requirements from User

Add Cosmos-Reason2-2B as a PyTorch BF16-only entry in the benchmark registry.
VLM inference path: image + text in, reasoning text out.

## Updates on User Requirements

Superseded by the broader `cosmos-reason2b` feature (docs/features/active/cosmos-reason2b/)
which implements both `hf_transformers` and `trt_edge_llm` runtimes with full
LingoQA accuracy evaluation — a superset of what this feature required.

## Design

See design.md.

## Tasks

- [x] Superseded by cosmos-reason2b feature

## Updates on Approved Plan

Closed without implementation. All goals are covered by cosmos-reason2b.
