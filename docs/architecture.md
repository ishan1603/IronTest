# IronTest System Architecture

## Overview
IronTest is a cutting-edge, autonomous QA pipeline driven by a multi-agent LLM infrastructure. It eliminates the manual QA bottleneck by instantly converting raw Jira stories into exhaustive, code-backed test suites and risk topographies.

## Architecture Topology

```mermaid
graph TD
    subgraph Frontend [React Platform]
        UI[Apple-Style Minimal UI]
        Stream[EventSource Listener]
        Dash[Dynamic Dashboard]
        UI --> Stream
        Stream --> Dash
    end

    subgraph Backend [FastAPI Engine]
        API[Post /api/analyze]
        Orch{Langchain Orchestrator}
        Mem[(Session State)]
        
        API --> Orch
        Orch <--> Mem
    end

    subgraph Artificial Intelligence [Agents]
        A1[🧠 Story Agent]
        A2[⚙️ Test Agent]
        A3[🔍 Defect Agent]
        
        Orch --> A1
        A1 --> A2
        A2 --> A3
    end
    
    UI -- "User Story" --> API
    A1 & A2 & A3 -. "Streaming SSE" .-> Stream
```

## Component Interplay
1. **The Entry Point**: The user initiates the sequence via the React frontend. The payload is sent to the FastAPI orchestration layer.
2. **The Orchestrator**: The backend spins up an isolated, async session. Using Server-Sent Events (SSE), it streams exact, real-time logs back to the user.
3. **Agent Handoffs**:
   - The **Story Agent** receives the raw string, outputting structured JSON (Intent Matrix).
   - The **Test Agent** reads the Intent Matrix, outputting an array of Test Vectors.
   - The **Defect Agent** reads all prior output, calculating the final deployment verdict.
4. **Data Visualization**: The final merged payload is pushed to the frontend, instantly rendering the interactive, Awwwards-style data dashboard.

## Technology Stack
- **Frontend**: React, Tailwind CSS, Framer Motion, Vite (Awwwards-style UI).
- **Backend**: Python 3.12+, FastAPI, Pydantic, HTTPX.
- **AI Core**: Groq AI (Llama 3), structured JSON extraction protocols.
