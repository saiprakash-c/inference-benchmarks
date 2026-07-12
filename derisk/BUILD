load("@pip//:requirements.bzl", "requirement")

py_binary(
    name = "derisk",
    srcs = ["derisk.py"],
    main = "derisk.py",
    deps = [
        requirement("torch"),
        requirement("torchvision"),
        requirement("transformers"),
        requirement("accelerate"),
        requirement("pillow"),
        requirement("safetensors"),
        requirement("huggingface-hub"),
        requirement("qwen-vl-utils"),
    ],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "derisk_cosmos_tensorrt_edge_llm",
    srcs = ["derisk_cosmos_tensorrt_edge_llm.py"],
    main = "derisk_cosmos_tensorrt_edge_llm.py",
    deps = [
        requirement("torch"),
        requirement("transformers"),
        requirement("pillow"),
        requirement("pyarrow"),
    ],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "derisk_metrics_cosmos_reason",
    srcs = ["derisk_metrics_cosmos_reason.py"],
    main = "derisk_metrics_cosmos_reason.py",
    deps = [
        requirement("torch"),
        requirement("torchvision"),
        requirement("transformers"),
        requirement("accelerate"),
        requirement("pillow"),
        requirement("safetensors"),
        requirement("huggingface-hub"),
        requirement("qwen-vl-utils"),
        requirement("pyarrow"),
    ],
    visibility = ["//visibility:public"],
)
