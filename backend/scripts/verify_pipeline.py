"""Exercises every agent against real providers and reports what happened.

Run it to confirm the four-agent pipeline actually works end to end -- not the
stubbed integration tests, but real LLM calls through the failover chain.

    python scripts/verify_pipeline.py            # one pass
    python scripts/verify_pipeline.py --runs 5   # stability check
    python scripts/verify_pipeline.py --story "Users can reset a password"

Uses the standalone path (no GitHub needed). Reads .env for provider keys.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from agents.defect_agent import analyze_defects  # noqa: E402
from agents.execution_agent import execute_tests  # noqa: E402
from agents.story_agent import analyze_story  # noqa: E402
from agents.test_agent import generate_tests  # noqa: E402
from llm import configured_providers  # noqa: E402

DEFAULT_STORY = (
    "As a shopper I want to apply a percentage discount code at checkout so that "
    "the order total is reduced. An expired code must be rejected with a clear "
    "message, and a code cannot take the total below zero."
)

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


class Capture(logging.Handler):
    """Grabs the 'LLM call served by x/y' lines the client logs."""

    def __init__(self) -> None:
        super().__init__()
        self.served: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "LLM call served by" in msg:
            self.served.append(msg.split("served by", 1)[1].strip())


async def _stage(name: str, coro):
    start = time.perf_counter()
    try:
        result = await coro
        return name, True, time.perf_counter() - start, result, ""
    except Exception as exc:  # noqa: BLE001
        return name, False, time.perf_counter() - start, None, f"{type(exc).__name__}: {exc}"


async def one_pass(story_text: str) -> bool:
    capture = Capture()
    logging.getLogger("llm.client").addHandler(capture)
    logging.getLogger("llm.client").setLevel(logging.INFO)

    rows: list[tuple[str, bool, float, str]] = []

    name, ok, secs, story, err = await _stage("story", analyze_story(story_text))
    rows.append((name, ok, secs, err or f"{len(story.modules)} modules, {len(story.acceptance_criteria)} criteria"))
    if not ok:
        _print_table(rows, capture.served)
        return False

    name, ok, secs, tests, err = await _stage("test", generate_tests(story, story_text=story_text))
    automated = sum(1 for t in tests for _ in [1] if t.automated)
    rows.append((name, ok, secs, err or f"{len(tests)} cases, {automated} runnable"))
    if not ok:
        _print_table(rows, capture.served)
        return False

    name, ok, secs, execution, err = await _stage("execution", execute_tests(tests))
    passed = sum(1 for r in execution.results if r.status == "pass")
    rows.append((name, ok, secs, err or f"{passed}/{len(execution.results)} passed ({execution.duration_seconds}s wall)"))
    if not ok:
        _print_table(rows, capture.served)
        return False

    name, ok, secs, defects, err = await _stage("defect", analyze_defects(story, tests, execution))
    rows.append(
        (name, ok, secs, err or f"score {defects.overall_confidence_score}, verdict {defects.deployment_recommendation}")
    )

    _print_table(rows, capture.served)
    return all(row[1] for row in rows)


def _print_table(rows, served) -> None:
    print()
    for name, ok, secs, detail in rows:
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {mark}  {BOLD}{name:<10}{RESET} {secs:6.1f}s  {DIM}{detail}{RESET}")
    if served:
        print(f"  {DIM}served by: {', '.join(served)}{RESET}")
    print()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--story", default=DEFAULT_STORY)
    args = parser.parse_args()

    providers = configured_providers()
    if not providers:
        print(f"{RED}No LLM provider configured.{RESET} Set a key in .env (GEMINI_API_KEY recommended).")
        return 2
    print(f"{DIM}providers: {', '.join(p.name for p in providers)}{RESET}")

    ok_count = 0
    for i in range(args.runs):
        if args.runs > 1:
            print(f"{BOLD}--- pass {i + 1}/{args.runs} ---{RESET}")
        if await one_pass(args.story):
            ok_count += 1

    summary_colour = GREEN if ok_count == args.runs else RED
    print(f"{summary_colour}{ok_count}/{args.runs} passes completed all four agents.{RESET}")
    return 0 if ok_count == args.runs else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
