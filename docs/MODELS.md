# MODELS

Supported models, input shapes, and precision support matrix.
Focus: vision models for robotics on Thor.
Every model listed here must have a corresponding benchmark target;
//ci:lint enforces this.

## Model Registry

Active precision: **FP32**. FP16/INT8/FP8 are planned but out of scope until models are stable.

| Model | Task | Input Shape (B, C, H, W) | Bazel target | FP32 | Status |
|---|---|---|---|---|---|
| ResNet50 | Image classification | (1, 3, 224, 224) | `//models/resnet50` | active | active |
| DINOv2-B | Vision encoder (robotics) | (1, 3, 518, 518) | `//models/dinov2_b` | planned | planned |


## Input Shape Convention

Shapes are expressed as `(batch, C, H, W)` for vision models and
`(batch, seq_len)` for language models. Batch size 1 is the default
for latency measurement; batch > 1 is used for throughput measurement.

## Adding a Model

1. Add a row to the table above (FP32 column only until other precisions are active)
2. Create `//models/<name>/` with input shape spec
3. Ensure each runtime in RUNTIMES.md has been tested with this model or is marked
   as unsupported for it
4. Run //ci:lint to verify consistency

