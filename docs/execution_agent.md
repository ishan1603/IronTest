# 🚀 Execution Agent

## Overview
The **Execution Agent** is responsible for taking AI-generated test snippets and running them in a live, isolated environment. This transforms IronTest from a documentation generator into a functional validation engine.

## Core Responsibilities
1. **Isolation**: Every test run occurs in a unique `TemporaryDirectory` to prevent file-system pollution.
2. **Resilience**: The agent automatically wraps raw code snippets into valid `pytest` functions if the LLM forgets the structure.
3. **Network Mocking**: Injects a global `sys.modules` stub for `requests` to stop real network calls and allow hallucinated domains (e.g., `vault-api.com`) to "work" during the demo.
4. **Dependency Stubbing**: Provides a `MockFactory` that handles common hallucinated objects like `payment_gateway` or `inventory` via `MagicMock`.

## How It Works
- **Subprocess Execution**: It spawns a `pytest` subprocess using `sys.executable -m pytest`.
- **Intelligent Feedback**: It captures `stdout` and `stderr`, truncating massive logs to provide concise failure evidence to the user.
- **Dynamic Realism**: If a URL contains keywords like `fail` or `error`, the internal stub will trigger a failure response (400/500), testing the system's ability to catch defects.

## Technical Details
- **Timeout**: Enforced **20s** timeout per test to ensure the environment remains responsive.
- **Reporting**: Outputs a unified `TestExecutionSummary` used by the Defect Agent for risk assessment.
