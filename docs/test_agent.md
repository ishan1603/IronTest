# Test Agent

## Overview
The **Test Agent** is where the actual test generation happens. It takes the structured requirements parsed by the Story Agent and figures out exactly what needs to be tested. We wanted to go beyond just the "happy path," so we instructed this agent to actively look for boundary conditions and edge cases.

## Core Responsibilities
1. **Test Case Generation**: Maps the acceptance criteria into clear, functional test steps.
2. **Edge Case Checking**: Specifically generates tests for boundary conditions, unusual inputs, and state changes.
3. **Code Snippet Generation**: Writes sample automation scripts (like Playwright or Selenium snippets) for the most critical tests, saving developers time.
4. **Risk Scoring**: Gives each test a quick risk and complexity score.

## Test Generation Flow
```mermaid
graph LR
    A[Structured Requirements] --> B(Path Analysis)
    B --> C[Happy Path]
    B --> D[Edge Cases]
    B --> E[Boundary Limits]
    C & D & E --> F{Vector Compilation}
    F --> G[Test Registry (JSON)]
    F --> H[Code Snippet Generation]
```

## Our Motivation
Writing tests for edge cases is tedious and often skipped during tight deadlines. By having an agent handle the heavy lifting of figuring out *what* could break, we can cover way more ground than standard manual testing, and give developers a tangible head start with copy-pasteable snippets.
