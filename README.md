<p align="center">
	<img src="frontend/public/favicon.svg" width="86" alt="IRONTEST logo" />
</p>

<h1 align="center"><strong>IRONTEST</strong></h1>

<p align="center">
	Production-ready autonomous QA intelligence platform that transforms stories into test intelligence, execution evidence, and release confidence.
</p>

<p align="center"><strong>Thank you Team ATOS for this challenging and fun hackathon experience.</strong></p>

## Screenshot Placeholder

<p align="center">
	<img src="../image.png" alt="IRONTEST application screenshot placeholder" />
</p>

## Why IRONTEST

- Multi-agent QA pipeline with stage-by-stage telemetry.
- Streaming updates over Server-Sent Events for live traceability.
- Cost-aware OpenRouter default model profile for hackathon usage.
- Resilient storage strategy with MongoDB primary and JSON fallback.

## Tech Stack

<table align="center">
	<tr>
		<td align="center"><strong>Frontend</strong><br/>React<br/>Vite<br/>Tailwind CSS<br/>Framer Motion</td>
		<td align="center"><strong>Backend</strong><br/>FastAPI<br/>Pydantic<br/>Requests<br/>Pytest</td>
		<td align="center"><strong>AI Gateway</strong><br/>OpenRouter<br/>openai/gpt-oss-120b:free<br/>Fallback candidates supported</td>
	</tr>
	<tr>
		<td align="center"><strong>Data</strong><br/>MongoDB primary<br/>history.json fallback</td>
		<td align="center"><strong>Integrations</strong><br/>Jira REST API v3</td>
		<td align="center"><strong>Runtime Pattern</strong><br/>SSE streaming orchestration<br/>Agent-by-agent telemetry</td>
	</tr>
</table>

## Architecture

### System Topology

```mermaid
graph TD
		UI[React Frontend] -->|POST /api/analyze| API[FastAPI Backend]
		UI -->|POST /api/ingest/jira| API
		UI <-->|SSE /api/stream/:session_id| API

		API --> ORCH[Pipeline Orchestrator]
		ORCH --> STORY[Story Agent]
		STORY --> TEST[Test Agent]
		TEST --> EXEC[Execution Agent]
		EXEC --> DEFECT[Defect Agent]

		STORY --> LLM[OpenRouter LLM]
		TEST --> LLM
		DEFECT --> LLM

		EXEC --> DB[(MongoDB)]
		DB -. fallback unavailable .-> JSON[(backend/data/history.json)]
		DEFECT --> DB
		DEFECT --> JSON
```

### Runtime Flow

```mermaid
sequenceDiagram
		participant U as User
		participant F as Frontend
		participant B as Backend API
		participant O as Orchestrator
		participant A as Agents
		participant D as Data Store

		U->>F: Submit story or Jira URL
		F->>B: POST /api/analyze
		B->>O: Create session and queue
		F->>B: GET /api/stream/:session_id

		O->>A: Run Story Agent
		A-->>B: Story intelligence
		B-->>F: SSE agent_complete

		O->>A: Run Test Agent
		A-->>B: Generated tests
		B-->>F: SSE agent_complete

		O->>A: Run Execution Agent
		A->>D: Persist execution history
		A-->>B: Execution summary
		B-->>F: SSE agent_complete

		O->>A: Run Defect Agent
		A-->>B: Confidence and recommendation
		B-->>F: SSE pipeline_complete
```

## Documentation Map

- Setup guide: [setup.md](setup.md)
- Full documentation: [docs](docs)
- Architecture deep dive: [docs/architecture.md](docs/architecture.md)
- Story agent: [docs/story_agent.md](docs/story_agent.md)
- Test agent: [docs/test_agent.md](docs/test_agent.md)
- Execution agent: [docs/execution_agent.md](docs/execution_agent.md)
- Defect agent: [docs/defect_agent.md](docs/defect_agent.md)
- Interface contract: [docs/interface.md](docs/interface.md)

## Quick Start

Follow [setup.md](setup.md) for complete local setup.

Minimum requirements:

- Python 3.12+
- Node.js 20+
- OPENROUTER_API_KEY
- Optional MongoDB and Jira credentials

## Production Configuration

See [.env.example](.env.example) for all supported variables.

Core variables:

- OPENROUTER_API_KEY
- OPENROUTER_MODEL_ID (default: openai/gpt-oss-120b:free)
- OPENROUTER_MODEL_CANDIDATES (fallback: openai/gpt-oss-20b:free)
- OPENROUTER_HTTP_REFERER
- OPENROUTER_APP_NAME
- MONGODB_URI
- MONGODB_DB_NAME
- MONGODB_COLLECTION
- JIRA_EMAIL
- JIRA_API_TOKEN

## API Surface

- POST /api/analyze
- GET /api/stream/{session_id}
- POST /api/ingest/jira
- POST /api/webhook/github
- GET /health

## Team 838

| Member | Responsibility | Scope                                                                |
| ------ | -------------- | -------------------------------------------------------------------- |
| Ishan  | Agents         | Story, Test, Execution, Defect agent logic and orchestration quality |
| Aryan  | Frontend       | UX flow, dashboards, pipeline visualization, interaction polish      |
| Meet   | Backend        | API reliability, integrations, persistence, deployment wiring        |
