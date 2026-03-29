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
- Renders a static site to site/ using a templating approach
- site/ is gitignored — it is always generated, never manually edited

## //site:deploy

- Pushes site/ to the gh-pages branch
- Runs only after //site:build exits 0
- Triggered automatically after a successful daily benchmark run (see CI.md)

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

GitHub Pages (static). Site is regenerated on each daily benchmark run and pushed
to the gh-pages branch by //site:deploy.
