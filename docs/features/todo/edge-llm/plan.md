# Plan: edge-llm
Status: awaiting approval

---

## Requirements from User

- Branch: `saip/edge-llm`
- Create an `experimental/` folder
- Write a simple C++ script that uses TensorRT-LLM C++ APIs to load and run
  Qwen2.5-0.5B-Instruct and stream the response to stdout
- Invoked via `bazel run //experimental:tutorial -- "can you explain tensor cores"`
- Code must be dead simple and easy to read — no advanced features yet
- No CLI tool wrappers; must use C++ APIs directly

## Updates on User Requirements

- Added `experimental/build_engine.sh` (manual, one-time step) to convert the
  HuggingFace checkpoint to a TRT-LLM engine. Not a Bazel target; documented in
  README. This is necessary because TRT-LLM requires a pre-built engine at runtime.
- Added `experimental/README.md` covering model download, engine build, and
  `bazel run` usage. Keeps the tutorial self-contained.
- Tokenization via `tensorrt_llm/common/tokenizer.h` (C++ only; no Python
  subprocess). If the header path differs in the installed package, Coder locates
  the correct path.

## Design

```
experimental/
  BUILD           ← cc_binary //experimental:tutorial
  tutorial.cpp    ← ~120 lines; Executor API + streaming
  build_engine.sh ← one-time: trtllm-build → /opt/models/qwen2.5-0.5b-trtllm-engine
  README.md       ← model download + engine build + run instructions
```

**Streaming call flow:**

```
argv[1] (prompt string)
  │
  ▼
Tokenizer::create(VOCAB_PATH)
  │  tokenizer.encode(prompt) → input_ids
  ▼
ExecutorConfig { max_beam_width=1 }
Executor       { ENGINE_DIR, config }
  │
  ▼
Request { input_ids, max_new_tokens=512, streaming=true }
executor.enqueueRequest(request) → requestId
  │
  ▼
loop: executor.awaitResponses(requestId)
  for each Response r:
    for each token: decode → print to stdout (flush)
    if r.isFinal(): break
```

**Key TRT-LLM types:**

| Type | Header | Purpose |
|---|---|---|
| `Executor` | `tensorrt_llm/executor/executor.h` | Main runtime handle |
| `ExecutorConfig` | same | Beam width, KV cache policy |
| `Request` | same | Prompt tokens + generation params |
| `Response` | same | Generated tokens + done flag |
| `Tokenizer` | `tensorrt_llm/common/tokenizer.h` | encode / decode |

**Compile-time constants:**
```cpp
const std::string ENGINE_DIR = "/opt/models/qwen2.5-0.5b-trtllm-engine";
const std::string VOCAB_PATH = "/opt/models/qwen2.5-0.5b/tokenizer.json";
```

**BUILD linkopts:** `-ltensorrt_llm`, `-lnvinfer`, `-lcuda`, `-lcudart`
Headers resolved from system include path inside the Docker image on Thor.

## Tasks

- [ ] Create branch `saip/edge-llm`
- [ ] Check whether `tensorrt_llm/executor/executor.h` and
      `tensorrt_llm/common/tokenizer.h` are present in the Thor Docker image;
      if not, add an install step to `README.md` (pip install tensorrt-llm or
      apt install, whichever applies)
- [ ] Create `experimental/BUILD` with `cc_binary` target `tutorial`
      (copts `-std=c++17`, linkopts as above)
- [ ] Write `experimental/tutorial.cpp` implementing the streaming flow above;
      keep it under 120 lines excluding includes; every non-obvious line gets
      a one-line comment
- [ ] Write `experimental/build_engine.sh` with the `trtllm-build` invocation
      for Qwen2.5-0.5B-Instruct (FP16, max_input_len=512, max_seq_len=1024)
- [ ] Write `experimental/README.md` covering:
      1. Download Qwen2.5-0.5B-Instruct weights from HuggingFace
      2. Run `build_engine.sh` once to produce the TRT-LLM engine
      3. `bazel run //experimental:tutorial -- "your prompt here"`
- [ ] Verify `bazel run //experimental:tutorial -- "can you explain tensor cores"`
      compiles and streams output on Thor
- [ ] Open PR against `main` from `saip/edge-llm`

## Updates on Approved Plan
_(append here after approval — never modify sections above)_
