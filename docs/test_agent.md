# Test Agent (⚙️ Vector Synthesizer)

## Overview
The **Test Agent** is the computational heart of IronTest. It ingests the structured `Intent Matrix` produced by the Story Agent and mathematically derives an exhaustive suite of test vectors. It operates far beyond simple "happy path" testing by explicitly hunting for boundary conditions and edge-case anomalies.

## Core Responsibilities
1. **Vector Generation**: Maps the acceptance criteria into distinct functional test cases.
2. **Boundary Stressing**: Intelligently creates tests that push numeric limits, state transitions, and temporal constraints.
3. **Automated Code Synthesis**: For critical vectors, it writes actual executable automation script snippets (e.g., Playwright or Selenium syntax) that engineers can instantly drop into their CI/CD pipeline.
4. **Risk Scoring**: Assigns an initial complexity and risk score to each test vector.

## The Generation Matrix
The agent cross-references the targeted microservices against a historic knowledge base of common failure patterns.

```mermaid
graph LR
    A[Structured Intent] --> B(Path Analysis)
    B --> C[Happy Path]
    B --> D[Edge Cases]
    B --> E[Boundary Limits]
    C & D & E --> F{Vector Compilation}
    F --> G[Test Registry (JSON)]
    F --> H[Code Snippet Generation]
```

## Why it's Revolutionary
Instead of a QA engineer spending hours reverse-engineering a feature, the Test Agent utilizes LLM-driven dimensional generation to cover 99% of edge cases in seconds, outputting them in instantly readable formats with copy-pasteable automation code.
