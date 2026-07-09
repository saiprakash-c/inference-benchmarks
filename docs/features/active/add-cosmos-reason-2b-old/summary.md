# Summary: add-cosmos-reason-2b
Completed: 2026-07-09

## What was built

Not implemented — superseded before any code was written.

## Deviations from plan

The scope was expanded: instead of PyTorch-only BF16 inference, the
`cosmos-reason2b` feature (docs/features/active/cosmos-reason2b/) implements
both `hf_transformers` and `trt_edge_llm` runtimes with LingoQA 500-sample
accuracy evaluation via Lingo-Judge.

## Lessons learned

- Feature naming with en-dashes (–) breaks Bazel's filegroup glob; use ASCII
  hyphens in directory names.
