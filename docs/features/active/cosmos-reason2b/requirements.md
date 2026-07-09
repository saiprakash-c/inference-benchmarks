# Requirements: cosmos-reason2b
Date: 2026-07-09

## Goal

Add Cosmos-Reason2-2B (VLM, Qwen3-VL backbone) to the benchmark harness with
two runtimes and LingoQA accuracy evaluation.

## Requirements

- Two new runtime implementations: `hf_transformers` (HuggingFace Transformers,
  native video tokenization) and `trt_edge_llm` (TensorRT Edge-LLM C++ engine
  via pybind11, temporal frame-pair fusion)
- Both runtimes follow the same `init/run/teardown/version/profile` pattern as
  existing runtimes (`pytorch`, `tensorrt`)
- Accuracy evaluation on LingoQA 500-sample eval set using Lingo-Judge scorer
- Results include `lingo_judge_mean` and `lingo_judge_pass_rate` fields
- Published to the static benchmark site under a new "VLM Benchmarks" section
- Baseline targets: hf_transformers ≥ 57% pass, trt_edge_llm ≥ 56% pass
