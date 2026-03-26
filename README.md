<div align="center">
  <img src="https://img.icons8.com/fluency/256/hexagon.png" width="80" alt="IronTest Logo"/>
  <h1>IronTest Autonomous QA Engine</h1>
  <p><strong>Transform fragmented Jira stories into production-ready test suites in 4.5 seconds.</strong></p>

  <p>
    <a href="https://reactjs.org/"><img src="https://img.shields.io/badge/React-18.2-blue?style=for-the-badge&logo=react" alt="React"></a>
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.110-009688?style=for-the-badge&logo=fastapi" alt="FastAPI"></a>
    <a href="https://tailwindcss.com/"><img src="https://img.shields.io/badge/Tailwind-3.4-38B2AC?style=for-the-badge&logo=tailwind-css" alt="Tailwind"></a>
    <a href="https://groq.com/"><img src="https://img.shields.io/badge/AI-Groq_Llama3-F6522E?style=for-the-badge" alt="Groq"></a>
  </p>
</div>

---

## 🚀 The Vision
QA is the last major bottleneck in modern software delivery. **IronTest** is a multi-agent artificial intelligence orchestrator designed to completely automate the QA engineering lifecycle. By deploying specialized, autonomous agents, it parses raw human intent, synthesizes edge-case test vectors, generates automation codes, and calculates mathematical deployment confidence—all wrapped in an Awwwards-winning, Apple-inspired interface.

## 🧠 The Multi-Agent Architecture
IronTest is powered by three specialized AI nodes working in sequential harmony:

1. **[Story Agent (Intent Architect)](docs/story_agent.md)**: Converts chaotic user stories into structured topological matrices.
2. **[Test Agent (Vector Synthesizer)](docs/test_agent.md)**: Maps intent to exhaustive functional, boundary, and edge test vectors, complete with automation snippets.
3. **[Defect Agent (Verdict Engine)](docs/defect_agent.md)**: Audits the generated suite to calculate a rigorous Go/No-Go deployment confidence score.

> 📚 **Deep Dive**: Check out the [docs/](./docs/) directory for detailed intelligence profiles and system architecture.

## 🎨 UI/UX Philosophy
We believe highly technical tools shouldn't look like spreadsheets. IronTest features:
- **Awwwards-Style Constraints**: Sub-pixel perfect minimalist typography and dynamic grid layouts.
- **Framer Motion Integration**: Liquid smooth transitions and zero-layout-shift streams.
- **Theme Native**: Flawless system-level Dark and Light mode toggling.

## ⚡ Getting Started
### Prerequisites
- Python 3.12+ 
- Node.js 20+
- A valid `GROQ_API_KEY`

### 1. Backend Spin-up
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements.txt
export GROQ_API_KEY="your-api-key"
uvicorn main:app --reload
```

### 2. Frontend Spin-up
```bash
cd frontend
npm install
npm run dev
```

Navigate to `http://localhost:5173` to experience IronTest.

## 📊 Deployment Flow
```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant FastAPI
    participant AI Ensemble
    
    User->>Frontend: Submit Raw Jira Ticket
    Frontend->>FastAPI: /api/analyze
    FastAPI->>AI Ensemble: Initiate Orchestration
    AI Ensemble-->>FastAPI: Stream Agent States (SSE)
    FastAPI-->>Frontend: Render Live Pipeline UI
    AI Ensemble-->>FastAPI: Final Consensus Payload
    FastAPI-->>Frontend: Display Tabbed QA Dashboard
```

## 🏆 Hackathon Ready
Built aggressively for modern engineering teams. IronTest bridges the gap between PM intent, engineering reality, and CI/CD automation.

<div align="center">
  <p><i>Design engineered for intelligence.</i></p>
</div>
