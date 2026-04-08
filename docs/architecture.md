# IRONTEST Architecture

## Overview

IRONTEST is a React + FastAPI autonomous QA platform that transforms product requirements into executable QA intelligence in four deterministic stages.

1. Story analysis
2. Test generation
3. Test execution
4. Defect intelligence and deployment verdict

## Runtime Topology

```mermaid
graph TD
    subgraph Frontend
        UI[React App]
        STREAM[SSE Event Stream]
        DASH[Pipeline and Dashboard Views]
        UI --> STREAM --> DASH
    end

    subgraph Backend
        API[FastAPI API]
        ORCH[Orchestrator]
        SESS[(Session Queue Manager)]
        API --> ORCH
        ORCH <--> SESS
    end

    subgraph Agent Chain
        STORY[Story Agent]
        TEST[Test Agent]
        EXEC[Execution Agent]
        DEFECT[Defect Agent]
        STORY --> TEST --> EXEC --> DEFECT
    end

    subgraph Integrations
        LLM[OpenRouter]
        JIRA[Jira REST API]
        MONGO[(MongoDB)]
        JSON[(history.json fallback)]
    end

    UI -->|POST /api/analyze| API
    UI -->|POST /api/ingest/jira| API
    API --> STORY
    STORY --> LLM
    TEST --> LLM
    DEFECT --> LLM
    EXEC --> MONGO
    MONGO -. unavailable .-> JSON
    DEFECT --> MONGO
    DEFECT --> JSON
    API -->|SSE /api/stream/:session_id| STREAM
    API --> JIRA
```

## Request Lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant OR as Orchestrator
    participant AG as Agents
    participant DB as Data

    U->>FE: Submit story
    FE->>BE: POST /api/analyze
    BE->>OR: Create async session
    FE->>BE: GET /api/stream/:session_id

    OR->>AG: Story Agent
    AG-->>BE: Structured story
    BE-->>FE: SSE event

    OR->>AG: Test Agent
    AG-->>BE: Test cases
    BE-->>FE: SSE event

    OR->>AG: Execution Agent
    AG->>DB: Persist run
    AG-->>BE: Execution summary
    BE-->>FE: SSE event

    OR->>AG: Defect Agent
    AG-->>BE: Confidence + verdict
    BE-->>FE: SSE pipeline_complete
```

## Integration Notes

- LLM provider: OpenRouter via backend/llm_client.py.
- Default model profile: openai/gpt-oss-120b:free with free-tier fallback candidates.
- Jira ingestion: Jira REST API v3 via backend/jira_client.py.
- Persistence: MongoDB with backend/data/history.json fallback for resilience.

## Operational Notes

- The application remains fully functional if MongoDB is unreachable.
- SSE delivery allows progressive UX updates while the pipeline is running.
- Agent outputs are normalized and validated before being rendered in UI.

## Related Docs

- Project setup: [../setup.md](../setup.md)
- Interface contract: [./interface.md](./interface.md)
- Story agent: [./story_agent.md](./story_agent.md)
- Test agent: [./test_agent.md](./test_agent.md)
- Execution agent: [./execution_agent.md](./execution_agent.md)
- Defect agent: [./defect_agent.md](./defect_agent.md)
