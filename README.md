# 🛂 Border Wait Live

A serverless AWS pipeline that records live wait times at Canada–US land border crossings every 15 minutes and serves them through a public API.

> 🚧 Work in progress.

## Why

The Canada Border Services Agency (CBSA) publishes **current** wait times, but its public **historical** data stopped being published at hourly detail after 2019 — recent years are only available as monthly summaries. This project collects the live feed continuously so hour-by-hour history exists again, starting with the Windsor–Detroit crossings.

## Architecture (planned)

```
EventBridge (every 15 min) ──▶ Collector Lambda ──▶ DynamoDB
                                                       │
                     Client ◀── Lambda Function URL ◀── Read API Lambda
```

- **AWS Lambda** (Python 3.12) for collection and the read API
- **Amazon DynamoDB** for time-series storage
- **Amazon EventBridge Scheduler** for the 15-minute schedule
- **AWS SAM** for infrastructure as code
- **GitHub Actions** for tests and deployment

## Data source

[Current Border Wait Times](https://open.canada.ca/data/en/dataset/d4a716f5-a2fc-4c3c-88ed-451fe05900e4) — CBSA, Open Government Licence – Canada.

## Status page

[`site/`](site/) is a static page that reads the API: current waits at the three Windsor–Detroit crossings with a 24-hour trend, plus a filterable table of every port of entry. It refreshes every minute and flags readings more than 3 hours old.

Until the API is deployed, it shows a sample built from a captured copy of the feed (`python scripts/build_sample.py`). To point it at the live API, set `window.BORDER_WAIT_API` in [`site/config.js`](site/config.js) to the stack's `ApiUrl` output, or open the page with `?api=<ApiUrl>`.

```bash
python -m http.server -d site 8000   # http://localhost:8000
```

## Deploying

See [docs/aws-setup.md](docs/aws-setup.md). GitHub Actions deploys with short-lived OIDC credentials after CI passes.
