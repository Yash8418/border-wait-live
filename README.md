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
