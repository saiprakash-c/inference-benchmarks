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
