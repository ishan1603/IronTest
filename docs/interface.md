# Interface Engine

## Overview

The frontend is designed for live, presentation-friendly observability of the multi-agent QA pipeline.

## Implemented UX Features

1. Hero input supports both preset vectors and manual story editing.
2. Jira import panel supports:
   - Jira URL
   - Jira email
   - Jira token
   - optional issue key override
3. Streaming pipeline cards show real-time agent status transitions.
4. Tabs separate pipeline telemetry, generated tests, and final score dashboard.
5. Export action downloads the final analysis payload as JSON.

## Reliability Improvements

- EventSource lifecycle is guarded to avoid false connection errors on intentional stream close.
- Pipeline header status now reflects active run vs standby state.
- Risk and table renderers include null/empty guards to prevent brittle UI crashes.

## Current Setup Note

- Current environment has GEMINI_API_KEY configured.
- MongoDB and Jira env credentials are still pending configuration.
- UI impact: Jira import works when credentials are provided in the form; history trends run from fallback JSON when MongoDB is not available.

## Visual System

- Glassmorphism card surfaces with light/dark support.
- Typing hero effect and animated system indicators for demo pacing.
- Heatmap + confidence gauge pairing for immediate release-readiness interpretation.
