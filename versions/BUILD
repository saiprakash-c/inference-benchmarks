load("@pip//:requirements.bzl", "requirement")

py_binary(
    name = "check",
    srcs = ["check.py"],
    main = "check.py",
    deps = [
        "//lib:log",
        requirement("tomli_w"),
    ],
    visibility = ["//visibility:public"],
)
