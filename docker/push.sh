#!/usr/bin/env bash
# //docker:push
# Pushes the benchmark image to GHCR and prints the digest.
# After running, record the digest in versions.toml [docker].digest.
#
# Requires: docker login ghcr.io (done automatically in CI via GITHUB_TOKEN)
#
# Usage:
#   bazel run //docker:push
#   IMAGE_TAG=ghcr.io/saiprakash-c/inference-benchmarks:20260328 bazel run //docker:push
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:-ghcr.io/saiprakash-c/inference-benchmarks:latest}"

# Log in to GHCR if GITHUB_TOKEN is set (skipped if already logged in locally)
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  echo "${GITHUB_TOKEN}" | docker login ghcr.io -u saiprakash-c --password-stdin
fi

echo "Pushing ${IMAGE_TAG} ..." >&2
docker push "${IMAGE_TAG}"

DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "${IMAGE_TAG}")

echo "" >&2
echo "Push complete." >&2
echo "Digest: ${DIGEST}" >&2
echo "" >&2
echo "Update versions.toml [docker]:" >&2
echo "  digest = \"${DIGEST}\"" >&2
