#!/usr/bin/env bash
# //docker:build
# Builds the benchmark Docker image for linux/arm64 (Thor / Jetson).
# After running, record the digest in versions.toml [docker].digest.
#
# Usage:
#   bazel run //docker:build
#   IMAGE_TAG=ghcr.io/saiprakash-c/inference-benchmarks:20260328 bazel run //docker:build
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:-ghcr.io/saiprakash-c/inference-benchmarks:latest}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Building ${IMAGE_TAG} ..." >&2

docker build \
  --platform linux/arm64 \
  -t "${IMAGE_TAG}" \
  -f "${REPO_ROOT}/docker/Dockerfile" \
  "${REPO_ROOT}"

# Digest is only available after push (local images don't have RepoDigests).
# Print the image ID for local verification; run //docker:push to get the digest.
IMAGE_ID=$(docker images --no-trunc --quiet "${IMAGE_TAG}")
echo "" >&2
echo "Build complete." >&2
echo "Image ID:  ${IMAGE_ID}" >&2
echo "Run 'bazel run //docker:push' to push and obtain the digest for versions.toml." >&2
