# Local Setup Guide

This guide explains how to run IronTest backend and frontend locally.

## 1) Prerequisites

- Python 3.12+
- Node.js 20+
- npm
- MongoDB (local instance or Atlas connection string, optional for now)

Optional for Jira ingestion:

- Jira account email
- Jira API token

## 2) Configure Environment

From the project root, copy environment template:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Edit .env and set at minimum:

- OPENROUTER_API_KEY

Current status on your machine:

- You are currently running with OPENROUTER_API_KEY.
- MongoDB and Jira environment variables are not added yet.
- This is supported: Mongo history automatically falls back to local JSON.

Recommended defaults:

- OPENROUTER_MODEL_ID=openai/gpt-oss-120b:free
- OPENROUTER_MODEL_CANDIDATES=openai/gpt-oss-20b:free
- OPENROUTER_HTTP_REFERER=http://localhost:5173
- OPENROUTER_APP_NAME=IronTest QA Agent
- USE_MONGODB=true (when MongoDB is ready)
- MONGODB_URI=mongodb://localhost:27017 (when MongoDB is ready)
- MONGODB_DB_NAME=irontest (when MongoDB is ready)
- MONGODB_COLLECTION=executions (when MongoDB is ready)

Optional for Jira import without typing credentials in UI:

- JIRA_EMAIL
- JIRA_API_TOKEN

## 3) Start MongoDB

Skip this section for now if you want OpenRouter-only mode.

Choose one option when you are ready.

Option A: Local MongoDB service

- Ensure your local MongoDB server is running on mongodb://localhost:27017

Option B: Docker MongoDB

```bash
docker run -d --name irontest-mongo -p 27017:27017 mongo:7
```

Option C: MongoDB Atlas

- Set MONGODB_URI to your Atlas URI in .env

## 4) Run Backend (FastAPI)

Open terminal 1:

```bash
cd backend
python -m venv .venv
```

Activate virtual environment.

Windows PowerShell:

```powershell
. .venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and start server:

```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

- Open http://localhost:8000/health
- Expected response: {"status":"ok"}

## 5) Run Frontend (Vite)

Open terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Open:

- http://localhost:5173

If needed, set frontend API endpoint in .env:

- VITE_API_BASE=http://localhost:8000

## 6) Verify End-to-End Flow

1. Open app at http://localhost:5173
2. Paste a manual story or import from Jira.
3. Click Initiate Analysis.
4. Confirm pipeline completes and score dashboard appears.
5. Confirm backend writes history to MongoDB collection.
6. If MongoDB is not configured, verify history updates in backend/data/history.json.

## 7) Optional: Run Full Stack With Docker Compose

From project root:

```bash
docker compose up --build
```

This starts:

- backend on http://localhost:8000
- frontend on http://localhost:5173
- mongo on mongodb://localhost:27017

## 8) Troubleshooting

- Missing OPENROUTER_API_KEY:
  - Backend /api/analyze returns 500. Set OPENROUTER_API_KEY in .env.

- Jira import fails with credentials error:
  - Provide Jira email and token in UI, or set JIRA_EMAIL and JIRA_API_TOKEN in .env.

- Mongo unavailable:
  - App continues using backend/data/history.json fallback, but persistent trending is limited.

- CORS or API base mismatch:
  - Ensure frontend points to backend at http://localhost:8000.
