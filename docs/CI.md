# CI

Daily cron, GitHub Actions jobs, and PR lifecycle.

## Repository

- `https://github.com/saiprakash-c/inference-benchmarks` (public)
- `main` branch protected; no direct pushes — all changes via PR
- Docker image: `ghcr.io/saiprakash-c/inference-benchmarks` (GitHub Container Registry)
- Thor is on Tailscale; its IP is discovered automatically via `tailscale status --json`
  — no static `THOR_HOST` variable. CI runners join the tailnet using `TAILSCALE_AUTH_KEY`.
- `gh` CLI authenticated via `GITHUB_TOKEN` (standard Actions token; PAT for local use)
- All benchmark targets run on Thor inside the Docker container via `//tools:ssh_run`
  (see AGENT_LOOP.md step 3a). GitHub Actions runners are used only for CI checks,
  not for benchmark execution.

## Check Architecture

Two distinct layers — do not conflate them:

| Layer | What | How | Speed |
|---|---|---|---|
| **Mechanical lint** (`//ci:lint`) | Target existence, schema conformance, no `print()`, append-only `results/` | Bazel rules | Seconds |
| **Semantic doc review** | Docs accurately describe the code; nothing stale or inconsistent | Agent in PR | ~1 min |

`//ci:lint` catches things that are unambiguously wrong and can be expressed as
deterministic rules. The agent PR review catches semantic drift that a linter
cannot — e.g. a runtime entry in RUNTIMES.md whose implementation no longer
matches its documented interface.

## Schedule

| Job | Trigger | Runner | Description |
|---|---|---|---|
| Daily benchmark | Cron midnight UTC | Thor (via SSH) | Full benchmark suite on latest versions |
| Mechanical lint | Every PR | GitHub runner | `//ci:lint` — fast deterministic checks |
| Agent doc review | Every PR | GitHub runner (agent) | Semantic doc/code consistency review |
| Doc gardening | Weekly (Monday 08:00 UTC) | GitHub runner (agent) | Drift scan, QUALITY_SCORE.md update, fix PRs |
| Site deploy | On merge to main | GitHub runner | `//site:build` + `//site:deploy` → GitHub Pages |

## Branch Naming

| Pattern | When to use |
|---|---|
| `benchmark/YYYY-MM-DD` | Daily benchmark result PRs |
| `feature/<name>` | PRs opened by the Coder agent for feature implementations. |
| `fix/doc-sync-<description>` | Self-correction PRs from agent doc review |
| `chore/version-bump-<runtime>` | PRs that update versions.toml for a new runtime release |

## GitHub Actions CI Checks

### On every PR

- Dev image build — required by lint/ruff/doc-review jobs; not a standalone gate
- `//ci:lint` — hard blocker (mechanical: target existence, schema, style rules)
- `//tools:validate_results` on any new files in `results/` — hard blocker (checks out LFS objects)
- Dockerfile lint (`hadolint`) — hard blocker
- Python lint (`ruff` via Bazel) — hard blocker
- Agent doc review — hard blocker (agent reads PR diff + affected docs, flags inconsistencies)

Note: the runtime image (GPU/arm64, targets Thor's sm_110a) is **not** built in CI —
it cannot run on GitHub's x86 ubuntu runners. Runtime image builds happen on Thor
as part of the daily benchmark workflow.

### On merge to main

- `//site:build`
- `//site:deploy` → GitHub Pages

### On daily cron (midnight UTC)

1. CI runner joins the Tailscale tailnet (`TAILSCALE_AUTH_KEY`)
2. `//tools:ssh_run` discovers Thor via `tailscale status --json`
3. Verifies container digest on Thor matches versions.toml `[docker].digest`
4. `bazel run //benchmark:run` inside container on Thor
5. Agent loop per AGENT_LOOP.md
6. Open PR with results if versions changed

## Agent PR Lifecycle

PRs are short-lived — open and merged within one agent session where possible.

**Happy path:**
1. Agent creates branch (`benchmark/YYYY-MM-DD` or appropriate pattern)
2. Agent commits results and updated versions.toml
3. Agent runs `//ci:lint` and `//tools:validate_results` locally before pushing
4. Agent opens PR via `gh pr create`
5. GitHub Actions runs `//ci:lint` + agent doc review automatically
6. If all checks pass: agent merges via `gh pr merge --squash --delete-branch`
   - If GitHub reports "not mergeable" despite all checks passing, wait 15–30s
     and retry — this is a propagation delay, not a real failure
   - Never use `--admin` to bypass branch protection; ask the human first

**On mechanical lint failure:**
1. Agent reads the error message — remediation instructions are embedded in every lint error
2. Agent self-corrects and pushes to the same branch
3. CI re-runs automatically
4. If the check fails again after the second push: escalate to human

**On agent doc review failure:**
1. Agent reads the reviewer's findings
2. Agent updates docs or code as indicated, pushes to the same branch
3. Agent doc review re-runs
4. If it fails again after the second attempt: escalate to human

**Human review** is opt-in and never on the critical path. Request it explicitly
by adding a reviewer; the agent never blocks on it by default.

## Merge Gates (Hard Blockers)

- `//ci:lint` must pass
- `//tools:validate_results` must pass (all results well-formed, no schema errors)
- Dockerfile lint (`hadolint`) must pass
- Python lint (`ruff`) must pass
- Agent doc review must pass

## Git LFS

Result files (`results/*.json`) and profile artifacts (`results/profiles/*`) are
stored in Git LFS. Git history holds small pointer files; LFS holds the actual
content. The `validate-results` CI job uses `lfs: true` on checkout to pull real
JSON for validation.

## Non-Blocking

- Test flakes — handled with a follow-up run, never a merge blocker
- QUALITY_SCORE.md staleness — flagged by doc_gardening, not a PR gate
- `docs/references/` content — lazily fetched, never a gate

## Branch Protection Rules on `main`

- `//ci:lint` must pass (hard block)
- `//tools:validate_results` must pass (hard block)
- Agent doc review must pass (hard block; fail-open if `ANTHROPIC_API_KEY` is absent)
- No required human reviewers — agent merges autonomously
- Branches deleted after merge

## GitHub Actions Secrets

Documented here and in `.env.example` at the repo root.

| Secret | Description |
|---|---|
| `THOR_SSH_KEY` | SSH private key *contents* (PEM) for logging into Thor |
| `TAILSCALE_AUTH_KEY` | Ephemeral Tailscale auth key; CI runner uses this to join the tailnet and reach Thor. Generate at tailscale.com/admin/settings/keys (ephemeral + reusable). |
| `GITHUB_TOKEN` | Standard Actions token; also authenticates GHCR push (`packages: write`). Passed to `//ci:doc_review` as the `GH_TOKEN` env var so `gh pr comment` can post findings. |
| `ANTHROPIC_API_KEY` | API key for the Claude SDK used by `//ci:doc_review`. Create at console.anthropic.com/settings/keys. Fail-open if absent — check is skipped, not blocked. |

`THOR_HOST` is **not** a secret — Thor's IP is discovered at runtime via `tailscale status`.
GHCR authentication uses `GITHUB_TOKEN`; no separate registry token is needed.

## Mechanical Lint Rules (`//ci:lint`)

Each error includes a remediation instruction so the agent can self-correct:

```
ERROR [lint/runtime-target-missing]: RUNTIMES.md lists 'aot_inductor' but no
target exists at //runtimes/aot_inductor/. Create the target or
remove the entry from RUNTIMES.md.

ERROR [lint/model-target-missing]: MODELS.md lists 'resnet50' but no target
exists at //models/resnet50/. Create the target or remove the entry
from MODELS.md.

ERROR [lint/print-statement]: print() call found in //runtimes/pytorch/runtime.py:42.
Use structured logging (see OBSERVABILITY.md).
# Note: only flags print() as a standalone statement at the start of a line.

ERROR [lint/results-mutation]: results/foo.json was modified. results/ is
append-only — existing files must not be mutated.

ERROR [lint/versions-schema]: versions.toml is missing required key [docker].digest.
```

## Commit Message Format

```
benchmark(runtime): description of what changed

runtime: <name> <version>
model: <name>
hw_id: <hardware identifier>
docker_image: sha256:<digest>
status: ok | anomaly | error
```

versions.toml and results/ are always committed together in a single commit.
