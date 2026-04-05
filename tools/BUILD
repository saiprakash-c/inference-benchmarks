load("@pip//:requirements.bzl", "requirement")

py_binary(
    name = "validate_results",
    srcs = ["validate_results.py"],
    main = "validate_results.py",
    deps = [
        "//lib:log",
        requirement("jsonschema"),
    ],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "ssh_run",
    srcs = ["ssh_run.py"],
    main = "ssh_run.py",
    deps = ["//lib:log"],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "verify_thor",
    srcs = ["verify_thor.py"],
    main = "verify_thor.py",
    deps = ["//lib:log"],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "update_quality",
    srcs = ["update_quality.py"],
    main = "update_quality.py",
    deps = ["//lib:log"],
    visibility = ["//visibility:public"],
)
