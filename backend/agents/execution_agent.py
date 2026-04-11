import tempfile
import subprocess
import time
import sys
import os
import asyncio
import textwrap
from typing import List

from models import TestCase, TestResult, TestExecutionSummary

async def execute_tests(tests: List[TestCase]) -> TestExecutionSummary:
    def _run() -> TestExecutionSummary:
        start_time = time.time()
        results = []
        
        with tempfile.TemporaryDirectory() as temp_dir:
            for t in tests:
                # Prioritize snippet presence; sometimes LLM sets automated=False but still provides code
                if not t.automation_snippet:
                    results.append(TestResult(test_id=t.id, status="skipped", error_message="Missing automation snippet"))
                    continue
                
                # Check if it's already a list or string
                if isinstance(t.automation_snippet, list):
                    snippet = "\n".join(t.automation_snippet)
                else:
                    snippet = str(t.automation_snippet)
                
                test_file = os.path.join(temp_dir, f"{t.id.replace('-', '_')}.py")
                with open(test_file, "w", encoding="utf-8") as f:
                    # Resilience: Wrap raw lines in a function if the LLM forgot to
                    if "def " not in snippet:
                        wrapped = "def test_generated_scenario():\n" + textwrap.indent(snippet, "    ")
                        f.write(wrapped)
                    else:
                        f.write(snippet)
                    
                try:
                    # Run pytest on the temporary file
                    proc = subprocess.run(
                        [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"], 
                        capture_output=True, 
                        text=True, 
                        timeout=20
                    )
                    
                    if proc.returncode == 0:
                        out = proc.stdout.strip()
                        if len(out) > 800:
                            out = "..." + out[-800:]
                        if not out:
                            out = "Test passed without additional logs."
                        results.append(TestResult(test_id=t.id, status="pass", error_message=out))
                    else:
                        # Extract the most relevant error part (tail of stdout)
                        err_out = proc.stdout.strip()
                        if not err_out:
                            err_out = proc.stderr.strip()
                        
                        # Just take the last 1000 characters to prevent massive logs
                        if len(err_out) > 1000:
                            err_out = "..." + err_out[-1000:]
                        
                        results.append(TestResult(test_id=t.id, status="fail", error_message=err_out))
                except subprocess.TimeoutExpired:
                    results.append(TestResult(test_id=t.id, status="error", error_message="Execution timeout exceeded (20s)"))
                except Exception as e:
                    results.append(TestResult(test_id=t.id, status="error", error_message=str(e)))

        duration = time.time() - start_time
        return TestExecutionSummary(results=results, duration_seconds=round(duration, 2))

    return await asyncio.to_thread(_run)
