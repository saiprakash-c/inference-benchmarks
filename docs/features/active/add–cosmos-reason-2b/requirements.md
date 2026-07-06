# Requirements: add Cosmos-Reason2-2B (VLM, PyTorch only)

## Goal

Add `cosmos_reason2_2b` as a model entry in the benchmark registry alongside
existing models such as `resnet50` and `dinov2`. PyTorch BF16 only.

VLM inference path only — image in, text reasoning out. No trajectory decoder,
no action head, no TRT engines.

-----

## Model

- **HuggingFace ID:** `nvidia/Cosmos-Reason2-2B`
- **Architecture:** Qwen3-VL-2B-Instruct post-trained for Physical AI reasoning
- **Precision:** BF16
- **Output:** text containing `<think>` reasoning trace + `<answer>` block

-----

## Model registration

Follow the same pattern as `resnet50` and `dinov2`. Implement the existing base
class. Do not modify the base class.

Add to `versions.toml`:

```toml
[models.cosmos_reason2_2b]
version   = "2"
hf_id     = "nvidia/Cosmos-Reason2-2B"
precision = "bf16"
```

-----

## Implementation

```python
import torch
import transformers

model = transformers.Qwen3VLForConditionalGeneration.from_pretrained(
    "nvidia/Cosmos-Reason2-2B",
    torch_dtype=torch.bfloat16,
    device_map="auto",
    attn_implementation="sdpa",
)
processor = transformers.AutoProcessor.from_pretrained("nvidia/Cosmos-Reason2-2B")
```

Measure `e2e_ms` with `torch.cuda.Event` from processor input preparation to
last generated token. Do not include model load time.

-----

## Test input

### Image

A crosswalk scene with a pedestrian visible. Use this public domain image:

```
URL:      https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/
          Simple_crosswalk.jpg/320px-Simple_crosswalk.jpg
Filename: test_crosswalk.jpg
```

Commit the image to the repo. Do not fetch at runtime.

### Prompt

```python
SYSTEM_PROMPT = (
    "You are a physical AI reasoning assistant. "
    "Answer in the following format:\n"
    "<think>\nyour reasoning\n</think>\n\n"
    "<answer>\nyour answer\n</answer>"
)

USER_PROMPT = (
    "A pedestrian is standing at the edge of a crosswalk ahead. "
    "The traffic light is amber. "
    "What should the ego vehicle do? "
    "Explain your reasoning step by step."
)

MAX_NEW_TOKENS = 512
TEMPERATURE    = 0.6
```

### Smoke test

```python
assert "<think>" in output and "<answer>" in output, (
    "Output missing CoT structure — check prompt format or max_new_tokens"
)
```

-----

## Metrics

```json
{
  "model":         "cosmos_reason2_2b",
  "runtime":       "pytorch",
  "precision":     "bf16",
  "e2e_ms":        <float>,
  "output_tokens": <int>
}
```

Include `output_tokens` — reasoning trace length is variable and `e2e_ms`
alone is not comparable across runs without it.

-----

## Constraints

- PyTorch BF16 only — no TRT, no Edge-LLM, no quantisation
- Do not modify the base class
- Do not add per-component timing in this PR
- Fail fast with a clear error if the HuggingFace model download fails
- Follow existing conventions in the repo for naming and placement

## Derisking

- done - path from bazel to pyproject
- done - will API of cosmos reason 2b jell well with our runtime? 
- image + text -> chat_template -> processor -> generate 
- 