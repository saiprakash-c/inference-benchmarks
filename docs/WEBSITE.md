# WEBSITE

How results flow from benchmark runs to the published static site.

## Pipeline

```
results/*.json
    ↓
//site:build  (aggregates + renders)
    ↓
site/         (generated static HTML/CSS/JS)
    ↓
//site:deploy (push to GitHub Pages)
    ↓
Published site (updated daily)
```

## //site:build

- Reads all JSON files from results/
- Aggregates by (runtime, model, precision) and computes trends
- Renders a static site to site/ using a templating approach (TBD pending
  decision stub 3 in initial-scaffold.md)
- site/ is gitignored — it is always generated, never manually edited

## //site:deploy

- Pushes site/ to the gh-pages branch
- Runs only after //site:build exits 0
- Triggered automatically after a successful daily benchmark run (see CI.md)

### Manual deployment procedure

Use HTTPS + `gh auth git-credential` (the token in `.env` is already configured).
The persistent clone at `/tmp/gh-pages-deploy` is pre-configured and persists
across sessions — reuse it, do not re-clone:

```bash
# 1. Pull latest gh-pages (in case it diverged)
git -C /tmp/gh-pages-deploy pull

# 2. Copy new site content
cp -r /workspace/site/public/. /tmp/gh-pages-deploy/

# 3. Commit and push
git -C /tmp/gh-pages-deploy add -A
git -C /tmp/gh-pages-deploy commit -m "deploy: <description>"
git -C /tmp/gh-pages-deploy -c credential.helper="!gh auth git-credential" push origin gh-pages
```

If `/tmp/gh-pages-deploy` is missing (e.g. after a reboot), re-create it once:
```bash
git -c credential.helper="!gh auth git-credential" clone --branch gh-pages --depth 1 \
    https://github.com/saiprakash-c/inference-benchmarks.git /tmp/gh-pages-deploy
```

## Site Content

The published site shows, for each (runtime, model, precision) combination:
- Latest latency (p50 + p99) and throughput
- Trend chart over the last 30 days
- Hardware and software version metadata for the latest run
- Status badge (ok / anomaly / error) for the latest run

## Adding a New Page

New pages (e.g. for a new model or new comparison view) are driven by
the data in results/ — no manual HTML editing. Add the template logic
to //site:build. The site regenerates on the next cron run.

## Hosting Decision

Pending resolution of decision stub 3 in docs/exec-plans/active/initial-scaffold.md.
Current default assumption: GitHub Pages (static). If dynamic hosting is chosen,
update this document and the //site:deploy implementation accordingly.
