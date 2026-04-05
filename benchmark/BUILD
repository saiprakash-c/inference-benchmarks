py_library(
    name = "registry",
    srcs = ["registry.py"],
    deps = [
        "//models/resnet50:spec",
        "//runtimes/pytorch:pytorch",
        "//runtimes/tensorrt:tensorrt",
        "//inputs:imagenet",
    ],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "run",
    srcs = ["runner.py"],
    main = "runner.py",
    deps = [
        "//benchmark:registry",
        "//hardware:thor",
        "//lib:log",
        "//runtimes/pytorch:pytorch",
        "//runtimes/tensorrt:tensorrt",
    ],
    visibility = ["//visibility:public"],
)
