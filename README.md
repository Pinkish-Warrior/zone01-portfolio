# 01Founders Portfolio

**[View live portfolio →](https://pinkish-warrior.github.io/zone01-portfolio/)**

An automated portfolio site built from my real progress at [01Founders](https://01founders.co) — XP growth, skill breakdown, audit history, and completed projects, pulled straight from the school's GraphQL API and published as a live, self-updating dashboard.

## Why this exists

01Founders (part of the 01 Edu / Zone01 network) uses peer-to-peer, project-based learning with no formal grading — progress is tracked through XP, audits, and project completions. This project turns that raw data into a portfolio I can point recruiters and collaborators to, instead of a static resume line.

It also doubles as a demonstration of practical engineering: API integration, data processing, front-end generation, and a CI/CD pipeline — all built from scratch.

## What it shows

- **XP growth over time** — charted progression through the curriculum
- **Skills by category** — radar/breakdown of technical competencies earned
- **Audit ratio** — peer-review activity (audits given vs. received), core to the 01Founders methodology
- **Top projects** — ranked by XP awarded
- **Full project & audit history**

## How it works

```
fetch_01founders.py  →  GraphQL API  →  raw JSON  →  processed stats  →  self-contained HTML report
```

1. `fetch_01founders.py` authenticates against the 01Founders GraphQL API using a JWT and pulls user profile, XP transactions, audits, and project progress.
2. The data is processed into summary stats and charts.
3. A single self-contained `index.html` (charts via Chart.js, no build step) is generated.
4. A GitHub Actions workflow (`.github/workflows/deploy.yml`) runs the exporter and publishes the result to GitHub Pages via `gh-pages`.

## Stack

Python (stdlib only — `urllib`, no external HTTP client), GraphQL, GitHub Actions, GitHub Pages, Chart.js.

## Running it yourself

```bash
cp .env.sample .env
# fill in JWT_TOKEN, STUDENT_LOGIN, STUDENT_ID — see .env.sample for how to grab your token
python fetch_01founders.py
```

This generates `<login>_01founders_portfolio.html` locally. In CI, the same script runs against secrets stored in the repo (`JWT_TOKEN`, `STUDENT_LOGIN`, `STUDENT_ID`) and deploys automatically on manual dispatch:

```bash
gh workflow run deploy.yml
```

Note: 01Founders JWTs expire periodically — if a scheduled/manual run fails with `JWTExpired`, refresh the `JWT_TOKEN` secret with a new token from the browser session.
