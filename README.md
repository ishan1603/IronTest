# IronTest Autonomous QA

Transform Jira tickets and product stories into test vectors, execution evidence, and a deployment confidence score.

## What Changed In This Version

- LLM stack migrated from Groq to Gemini with a shared JSON client.
- Real Jira ingestion implemented using Jira REST API v3.
- MongoDB-backed history enabled for long-term trend and regression analysis (with local JSON fallback).
- Defect scoring improved with blended logic across model output, current execution, and historical pass-rate trends.
- Frontend stability updates for stream lifecycle, manual story editing, and Jira import UX.

## Core Pipeline

1. [Story Agent](docs/story_agent.md): converts story text into structured risk-aware requirements.
2. [Test Agent](docs/test_agent.md): generates functional, boundary, edge, and regression tests.
3. [Execution Agent](docs/execution_agent.md): runs generated snippets in an isolated pytest environment.
4. [Defect Agent](docs/defect_agent.md): computes module risks and a deployment verdict from live + historical signals.

System architecture details are in [docs/architecture.md](docs/architecture.md).

## Local Setup

Use [setup.md](setup.md) for complete local setup instructions on Windows, macOS, and Linux.

Quick requirements:

- Python 3.12+
- Node.js 20+
- GEMINI_API_KEY
- MongoDB (local or Atlas, optional for now)
- Optional Jira credentials (JIRA_EMAIL, JIRA_API_TOKEN)

## Current Local Environment Status

This repository is currently being run in a Gemini-only local mode.

- Configured now: GEMINI_API_KEY only.
- Pending user-side setup: MongoDB variables and Jira credentials.

What this means right now:

- Pipeline runs with Gemini as expected.
- Historical persistence falls back to backend/data/history.json when MongoDB is not configured or reachable.
- Jira ingestion endpoint requires credentials in request body (or env vars once added).

## API Endpoints

- POST /api/analyze
- GET /api/stream/{session_id}
- POST /api/ingest/jira
- POST /api/webhook/github
- GET /health

## Environment Variables

See [.env.example](.env.example) for all supported settings.

Key variables:

- GEMINI_API_KEY
- GEMINI_MODEL_ID (default: gemini-2.5-flash)
- GEMINI_MODEL_CANDIDATES (comma-separated failover list)
- USE_MONGODB (optional for now)
- MONGODB_URI (optional for now)
- MONGODB_DB_NAME (optional for now)
- MONGODB_COLLECTION (optional for now)
- JIRA_EMAIL (optional for now)
- JIRA_API_TOKEN (optional for now)

## Notes

- For student-friendly usage, the backend defaults to gemini-2.5-flash and can fail over across GEMINI_MODEL_CANDIDATES (for example gemini-2.5-flash-lite, gemini-1.5-flash-8b) when one model hits quota or parsing issues.
- If MongoDB is unavailable, execution history falls back to backend/data/history.json so the app remains usable.
