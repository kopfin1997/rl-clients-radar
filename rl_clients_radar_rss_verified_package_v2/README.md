# RL Clients Radar · RSS Verified v2

This package is now structured to feel closer to a maintainable product than a one-off prototype.

## What changed

- Expanded client coverage to 15 tracked clients
- Expanded source registry with official pages, broad Google News RSS, and targeted trusted-publisher queries
- Added `data/clients.json` so client keywords, categories, and short labels live in data instead of Python code
- Added cover-image fetching into the pipeline and image rendering in the dashboard
- Added category-aware, data-driven dashboard filters and coverage views

## Package structure

- `index.html`: dashboard UI
- `data/clients.json`: client metadata, categories, keywords, short names
- `data/sources.json`: source registry and verification policy
- `data/headlines.json`: generated output payload
- `scripts/fetch_headlines.py`: fetch + enrich + dedupe pipeline

## Run locally

```bash
pip install -r requirements.txt
python scripts/fetch_headlines.py
python scripts/build_standalone.py
python -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

The generated single-file export will be:

```text
standalone.html
```

## Real images and real-time updates

- `index.html` is the live dashboard view. It reads `data/headlines.json`, so it stays fresh whenever that file is refreshed.
- `standalone.html` is a snapshot. It does not update by itself after export; regenerate it after each fetch.
- Real images come from the fetch pipeline:
  - RSS-native media fields first
  - Nearby page/card images next
  - `og:image` / `twitter:image` metadata as fallback

## Automation

The package includes `.github/workflows/update-radar.yml`.

It will:

1. install dependencies
2. run `scripts/fetch_headlines.py`
3. run `scripts/build_standalone.py`
4. commit refreshed `data/headlines.json` and `standalone.html`

Default schedule:

- every 6 hours

If you want tighter freshness, change the cron expression in the workflow.

## Current design choices

- Official sources are always preferred when deduplicating
- Third-party RSS is filtered through keyword match plus optional publisher/domain allowlists
- Cover images prefer feed-native media first, then nearby page images, then `og:image`/`twitter:image`
- The dashboard can still show tracked clients and configured sources even before a fresh fetch has been run
