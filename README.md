# ATOS — Autonomous AI Testing Agent for Context-Aware Release Validation

ATOS is a full-stack demo that simulates a virtual QA engineer embedded in a DevOps pipeline. It ingests a Jira-style user story, runs it through three Anthropic Claude agents (Story Intelligence, Test Generation, Defect Intelligence), and streams live progress to a Release Intelligence Dashboard with confidence gauge, risk heatmap, test table, and deployment verdict.

## Quick Start (under 5 steps)

1. Install dependencies

- Backend: `cd backend && pip install -r requirements.txt`
- Frontend: `cd frontend && npm install`

2. Export your Hugging Face token: `export HUGGINGFACE_API_TOKEN=hf_...` (PowerShell: `$env:HUGGINGFACE_API_TOKEN="hf_..."`). Optional: set `HUGGINGFACE_MODEL_ID` (default `tiiuae/falcon-7b-instruct`).
3. Run backend: `cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000`
4. Run frontend: `cd frontend && npm run dev -- --host --port 5173`
5. Open http://localhost:5173 and click a preset story, then Run Analysis.

### Docker Compose (single command)

```
docker-compose up --build
```

Frontend at http://localhost:5173, backend at http://localhost:8000.
Set env vars for compose: `HUGGINGFACE_API_TOKEN=hf_...` and optional `HUGGINGFACE_MODEL_ID`.

## Architecture

```
[React + Tailwind UI]
    |  POST /api/analyze (user story)
    |  GET  /api/stream/{session}  <-- SSE live agent events
[FastAPI Orchestrator]
    |-- Story Intelligence Agent (Hugging Face Inference API via router.huggingface.co)
    |-- Test Generation Agent     (Hugging Face Inference API via router.huggingface.co)
    |-- Defect Intelligence Agent (Hugging Face Inference API via router.huggingface.co)
    `--> Pipeline dashboard payload -> frontend visuals
```

## Key Innovation Points

- Multi-agent Anthropic pipeline with live SSE updates (no mock data)
- Enterprise dark UI: animated pipeline, radial confidence gauge, risk heatmap, filterable test table
- Deterministic, judge-proof demo flow with preset high-signal stories
- Clear failure handling (missing API key, stream errors) with graceful UI messaging
- Docker-compose ready; optional Vite dev mode for rapid iteration

## Environment

- Requires `ANTHROPIC_API_KEY` exported in shell or docker-compose environment
- Backend: FastAPI, SSE streaming; Frontend: React + Tailwind + Recharts + Framer Motion
