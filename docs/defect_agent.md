# Defect Agent

## Overview

The Defect Agent is the final risk layer. It combines current execution outcomes with historical data to produce module-level risk and a deployability verdict.

## Implemented Responsibilities

1. Pull module and global history stats from database.py.
2. Evaluate execution outcomes from TestExecutionSummary.
3. Ask OpenRouter for risk interpretation and critical test prioritization.
4. Validate score/recommendation output and return final recommendation payload.

## Data Inputs

- Story modules
- Generated tests (without full snippet payload)
- Execution summary (pass/fail/error)
- Historical module stats (defect probability, runs, pass rate)
- Historical global stats (average and recent pass rate)

## Confidence Logic

The final score currently uses the validated LLM-provided confidence score (0-100).
Historical and execution data are provided to the model as context for this prediction.

Recommendation is then mapped to GO, CONDITIONAL GO, or NO-GO with conservative behavior when execution errors are present.

## Persistence Dependency

- Primary source: MongoDB collection configured by MONGODB_URI, MONGODB_DB_NAME, MONGODB_COLLECTION.
- Fallback source: backend/data/history.json when MongoDB is not reachable.

## Flow

```mermaid
graph TD
    A[Execution Summary] --> D[Defect Agent]
    B[Module History] --> D
    C[Global Trend Stats] --> D
    D --> E[Module Risks]
    D --> F[Confidence Score]
    D --> G[Deployment Recommendation]
```
