# ATOS — Autonomous AI Testing Agent for Context-Aware Release Validation

ATOS is a full-stack demo that simulates a virtual QA engineer. It ingests a Jira-style user story, runs it through three Groq-backed agents (Story Intelligence, Test Generation, Defect Intelligence), and streams live progress to a release dashboard with a confidence gauge, risk heatmap, test table, and deployment verdict.

## Quick Start

1) Install deps
- Backend: `cd backend && py -3.11 -m venv .venv && .\.venv\Scripts\Activate && pip install -r requirements.txt`
- Frontend: `cd frontend && npm install`

2) Set env
- Required: `GROQ_API_KEY=<your_key>`
- Optional: `GROQ_MODEL_ID` (default `llama-3.1-8b-instant`; e.g., `llama-3.3-70b-versatile`)

3) Run
- Backend: `cd backend && .\.venv\Scripts\Activate && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- Frontend: `cd frontend && npm run dev -- --host --port 5173`
- Open http://localhost:5173, choose a preset story, Run Analysis.

### Docker Compose

```
docker-compose up --build
```

Frontend: http://localhost:5173, Backend: http://localhost:8000. Provide envs to compose: `GROQ_API_KEY`, optional `GROQ_MODEL_ID`.

## How it Works

1) User story intake
- React UI (Vite + Tailwind) provides preset Jira-like stories or manual input. The textarea can lock to a sample for deterministic demos.

2) Kickoff
- Frontend calls `POST /api/analyze` with the story; receives a `session_id`.

3) Live streaming
- Frontend opens `GET /api/stream/{session_id}` (SSE). Events drive the animated pipeline (Story → Tests → Defects) and show agent statuses.

4) Agents (Groq chat completions)
- Story Intelligence: extracts intent, modules (3–6), acceptance criteria, risks. Enforced JSON via `response_format`.
- Test Generation: produces 10–15 structured test cases (functional, boundary, edge, regression) keyed as `test_cases`.
- Defect Intelligence: scores module risk, computes overall confidence, deployment recommendation, critical tests. Enforced JSON via `response_format`.

5) Orchestration
- FastAPI orchestrator (see `backend/agents/orchestrator.py`) runs agents sequentially, emits `agent_start`, `agent_complete`, `pipeline_complete`, and `error` events over SSE. Errors bubble to UI toasts.

6) Dashboard
- Frontend renders confidence gauge (RadialBar), risk heatmap per module, filterable test table (by type/risk), and deployment verdict. Users can download the full JSON report from the dashboard.

## Architecture

```
[React + Vite + Tailwind + Framer Motion]
    |  POST /api/analyze (user story)
    |  GET  /api/stream/{session}  <-- SSE live agent events
[FastAPI Orchestrator]
    |-- Story Intelligence (Groq chat completion)
    |-- Test Generation    (Groq chat completion, json_object enforced)
    |-- Defect Intelligence (Groq chat completion, json_object enforced)
    `--> Dashboard payload -> frontend visuals (confidence, heatmap, tests, verdict)
```

## Environment

- `GROQ_API_KEY` (required)
- `GROQ_MODEL_ID` (default `llama-3.1-8b-instant`; alt `llama-3.3-70b-versatile`)
- Frontend uses `VITE_API_BASE` (optional; default `http://localhost:8000`).

## Notes

- Structured outputs: agents request `response_format: { type: "json_object" }` to minimize parsing errors; fallbacks guard against stray text.
- UI polish: aurora/glassmorphism background, animated pipeline, quick “Download report (JSON)” button after completion.
- Presets: curated Jira-like stories for deterministic demos; toggle to lock/unlock sample story for live edits.
