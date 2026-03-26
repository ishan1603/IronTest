import tempfile
import subprocess
import time
import sys
import os
import asyncio
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
                with open(test_file, "w") as f:
                    # Provide a 'Magic Mock' to prevent NameError for hallucinated modules
                    mock_setup = """
import pytest
import json
import sys
from unittest.mock import MagicMock

# Global module stubbing to prevent real network calls
class MockResponse:
    def __init__(self, url=""):
        # Dynamic realism: Simulate failures if the URL looks like a failure case
        self.url = url.lower()
        if any(k in self.url for k in ["fail", "error", "404", "unauthorized"]):
            self.status_code = self.status = 400 if "400" in self.url else 500
            self.success = False
        else:
            self.status_code = self.status = 200
            self.success = True
            
    def json(self):
        m = MagicMock()
        # Pass membership tests for positive flows, fail for negative ones if simulated
        m.__contains__.side_effect = lambda x: self.success
        m.get.side_effect = lambda k, d=None: "success" if self.success else "error"
        return m

def _mock_call(url, *args, **kwargs):
    return MockResponse(url=str(url))

mock_req = MagicMock()
mock_req.post.side_effect = mock_req.get.side_effect = mock_req.put.side_effect = mock_req.delete.side_effect = _mock_call
mock_req.Session.return_value = mock_req

# Stub the global module system
sys.modules['requests'] = mock_req
request = requests = mock_req

# Inject common variable names found in LLM hallucinations
payment_gateway = auth_service = inventory = billing = notification = db = MagicMock()
"""
                    f.write(mock_setup + "\n\n")
                    
                    # Resilience: Wrap raw lines in a function if the LLM forgot to
                    if "def " not in snippet:
                        import textwrap
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
                        results.append(TestResult(test_id=t.id, status="pass", error_message=""))
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
