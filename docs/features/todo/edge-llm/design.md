# Design: edge-llm
Date: 2026-06-26
Status: awaiting review

---

## Goal

Build a minimal, readable C++ tutorial that calls the TensorRT-LLM C++ Executor
API to load a Qwen model and stream token output to stdout.
Entry point: `bazel run //experimental:tutorial -- "can you explain tensor cores"`

---

## Scope

**In scope:**
- One C++ source file (`experimental/tutorial.cpp`)
- One Bazel BUILD file (`experimental/BUILD`)
- A small shell helper to build the TRT-LLM engine before running (`experimental/build_engine.sh`)
- README explaining how to obtain the model weights and build the engine

**Out of scope:**
- Speculative decoding, paged attention, multi-GPU — deferred to later iterations
- Python-side tokenization wrappers
- Integration with the existing benchmark harness

---

## Model choice

Model: **Qwen2.5-0.5B-Instruct** (0.5 B params, ~1 GB FP16). Thor has ample
memory; no fallback needed.

---

## TRT-LLM C++ API — chosen entry point

TensorRT-LLM exposes two C++ levels:

```
┌───────────────────────────────────────────────────────┐
│  High-level:  tensorrt_llm::executor::Executor        │  ← we use this
│    - Request / Response objects                        │
│    - streaming via awaitResponses()                    │
│    - handles batching, KV-cache internally             │
├───────────────────────────────────────────────────────┤
│  Low-level:  GptSession / TllmRuntime                 │
│    - tensor management by hand                        │
│    - unnecessary complexity for a tutorial            │
└───────────────────────────────────────────────────────┘
```

Header: `<tensorrt_llm/executor/executor.h>`
Key types used:

```
ExecutorConfig   — max_beam_width, kv_cache config, scheduler policy
Executor         — constructed from engine path + executor config
Request          — input_token_ids, max_new_tokens, streaming=true
Response         — token(s) generated so far + done flag
```

---

## Tokenization

TensorRT-LLM ships a C++ tokenizer wrapper around HuggingFace `tokenizers`
(via `tensorrt_llm/common/tokenizer.h`). Using it avoids a Python subprocess
while keeping the code self-contained.

```
Tokenizer::create(vocab_path)   → Tokenizer
tokenizer.encode(prompt_str)    → std::vector<int32_t>
tokenizer.decode({token_id})    → std::string   (called per token for streaming)
```

The `vocab_path` points to `tokenizer.json` from the HuggingFace model card.

---

## Streaming flow

```
main(argc, argv)
  │
  ├─ parse argv[1] as prompt string
  │
  ├─ Tokenizer::create(VOCAB_PATH)
  ├─ tokenizer.encode(prompt)   → input_ids
  │
  ├─ ExecutorConfig  { streaming=true, max_beam_width=1 }
  ├─ Executor        { ENGINE_DIR, ExecutorConfig }
  │
  ├─ Request { input_ids, max_new_tokens=512, streaming=true }
  ├─ executor.enqueueRequest(request)  → requestId
  │
  └─ loop: executor.awaitResponses(requestId)
        for each Response r:
          for each token in r.getTokens():
            decode + print to stdout (flush after each token)
          if r.isFinal(): break
```

Total C++ code target: **< 120 lines** (excluding includes).

---

## Compile-time paths (constants in tutorial.cpp)

```cpp
const std::string ENGINE_DIR  = "/opt/models/qwen2.5-0.5b-trtllm-engine";
const std::string VOCAB_PATH  = "/opt/models/qwen2.5-0.5b/tokenizer.json";
```

These are hard-coded for simplicity. A later iteration can accept them as flags.

---

## Bazel BUILD structure

```
experimental/
  BUILD
  tutorial.cpp
  build_engine.sh   ← not a Bazel target; run manually once before bazel run
  README.md
```

`BUILD`:
```python
cc_binary(
    name = "tutorial",
    srcs = ["tutorial.cpp"],
    copts = ["-std=c++17"],
    linkopts = [
        "-ltensorrt_llm",
        "-lnvinfer",
        "-lcuda",
        "-lcudart",
    ],
    # TRT-LLM headers expected at system include path inside the Docker image
)
```

The Docker image on Thor already has TensorRT-LLM installed; no `deps` pointing
at a Bazel-built TRT-LLM are needed.

---

## Engine build (one-time, manual)

`build_engine.sh` runs `trtllm-build` to convert the HuggingFace checkpoint to
a TRT-LLM engine. This is a one-time step, not part of `bazel run`.

```bash
# Inside the Docker container on Thor
trtllm-build \
  --checkpoint_dir /opt/models/qwen2.5-0.5b \
  --output_dir     /opt/models/qwen2.5-0.5b-trtllm-engine \
  --gemm_plugin float16 \
  --max_input_len  512 \
  --max_seq_len    1024
```

---

## File map

```
experimental/
  BUILD              ← cc_binary //experimental:tutorial
  tutorial.cpp       ← ~120-line C++ using Executor API
  build_engine.sh    ← one-time engine build command (documentation / manual step)
  README.md          ← model download + engine build + bazel run instructions
```

---

## Docker image

If the current Thor image does not have TensorRT-LLM C++ headers, the
`build_engine.sh` helper will also install TRT-LLM inside the container
(or the Docker image will be updated to include it). The Coder must verify
whether `tensorrt_llm/executor/executor.h` is present and add an install
step to `README.md` if it is not.

---

## Tokenization

`tensorrt_llm/common/tokenizer.h` is the required approach — no Python
subprocess fallback. If the header is not exposed in the installed package,
the Coder must locate the correct public header path for the installed
TRT-LLM version and use it directly from C++.
