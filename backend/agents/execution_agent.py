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
                with open(test_file, "w") as f:
                    # Provide a 'Magic Mock' to prevent NameError for hallucinated modules
                    mock_setup = """
import pytest
import json
import sys
import types
from datetime import datetime
from unittest.mock import MagicMock

# Global module stubbing to prevent real network calls
class MockResponse:
    def __init__(self, url="", method="get", body=None):
        self.url = str(url).lower()
        self.method = str(method).lower()
        self.body = body
        token = f"{self.url} {str(body).lower()}"

        def _tokenize_status(payload):
            if not isinstance(payload, dict):
                return 400

            # Alternate schema produced by model: card_details + customer_id
            if "card_details" in payload:
                details = str(payload.get("card_details", "")).strip().lower()
                if not details:
                    # Simulated known defect: empty card_details occasionally slips through validation.
                    return 200
                if "invalid" in details:
                    return 400
                return 200

            required = ["card_number", "expiry_month", "expiry_year", "cvv"]
            if any(not str(payload.get(k, "")).strip() for k in required):
                return 400

            card = str(payload.get("card_number", "")).strip()
            if (not card.isdigit()) or len(card) != 16:
                return 400

            cvv = str(payload.get("cvv", "")).strip()
            if (not cvv.isdigit()) or len(cvv) not in (3, 4):
                return 400

            try:
                month = int(str(payload.get("expiry_month", "0")).strip())
                year = int(str(payload.get("expiry_year", "0")).strip())
            except ValueError:
                return 400

            if month < 1 or month > 12:
                return 400

            now = datetime.now()
            if year < now.year or (year == now.year and month < now.month):
                return 400

            return 200

        self.status_code = 200
        self._error = ""
        if "tokenize" in self.url:
            self.status_code = _tokenize_status(body)
            if self.status_code == 400:
                details = str((body or {}).get("card_details", "")).strip().lower() if isinstance(body, dict) else ""
                if details == "":
                    self._error = "card details cannot be empty"
                elif "invalid" in details:
                    self._error = "invalid card details"
                else:
                    self._error = "invalid request"
            elif isinstance(body, dict) and str(body.get("card_details", "")).strip() == "":
                self._error = "known validation gap on empty card details"
        elif "/card_details/" in self.url:
            token_part = self.url.rsplit("/", 1)[-1]
            if any(k in token_part for k in ["invalid", "unauthorized", "expired"]):
                self.status_code = 401
                self._error = "unauthorized"
        elif "/customer/" in self.url:
            self.status_code = 200
        elif any(k in token for k in ["downtime", "service-down"]):
            self.status_code = 500
            self._error = "upstream dependency unavailable"
        elif any(k in token for k in ["notfound", "nonexist", "404"]):
            self.status_code = 404
            self._error = "not found"
        elif any(k in token for k in ["fail", "error", "invalid", "expired", "unauthorized", "denied"]):
            self.status_code = 400
            self._error = "invalid request"
        elif any(k in token for k in ["internal", "crash", "500"]):
            self.status_code = 500
            self._error = "internal error"

        self.status = self.status_code
        self.ok = self.status_code < 400
        self.success = self.ok

        self._payload = {
            "status": "success" if self.ok else "error",
            "success": self.ok,
            "locked": self.ok,
            "triggered": self.ok,
            "card_details": "expected_details" if self.ok else "",
            "card_id": "123456" if self.ok else "",
            "message": "ok" if self.ok else (self._error or "simulated failure"),
            "defect": None if self.ok else "simulated",
        }
        if self.ok:
            self._payload["token"] = "tok_123"
            if isinstance(body, dict):
                customer_id = body.get("customer_id")
                if customer_id:
                    self._payload["customer_id"] = customer_id
            if "/customer/" in self.url:
                self._payload["tokens"] = ["tok_123", "tok_abc"]
        else:
            self._payload["error"] = self._error or "simulated failure"
        self.text = json.dumps(self._payload)

    def json(self):
        return dict(self._payload)

def _mock_call(url, *args, **kwargs):
    body = kwargs.get("json") or kwargs.get("data")
    method = kwargs.get("method", "get")
    return MockResponse(url=str(url), method=method, body=body)

mock_req = MagicMock()
mock_req.get.side_effect = lambda url, *a, **k: _mock_call(url, *a, method="get", **k)
mock_req.post.side_effect = lambda url, *a, **k: _mock_call(url, *a, method="post", **k)
mock_req.put.side_effect = lambda url, *a, **k: _mock_call(url, *a, method="put", **k)
mock_req.delete.side_effect = lambda url, *a, **k: _mock_call(url, *a, method="delete", **k)
mock_req.Session.return_value = mock_req

# Basic playwright stub so browser-oriented snippets don't crash during import.
class _PWPage:
    def goto(self, url, *args, **kwargs):
        return MockResponse(url=url, method="goto")

class _PWBrowser:
    def new_page(self):
        return _PWPage()

class _PWChromium:
    def launch(self, *args, **kwargs):
        return _PWBrowser()

class _PWContext:
    def __init__(self):
        self.chromium = _PWChromium()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

def sync_playwright():
    return _PWContext()

playwright_mod = types.ModuleType("playwright")
sync_api_mod = types.ModuleType("playwright.sync_api")
sync_api_mod.sync_playwright = sync_playwright
playwright_mod.sync_api = sync_api_mod

# Stub the global module system
sys.modules['requests'] = mock_req
sys.modules['playwright'] = playwright_mod
sys.modules['playwright.sync_api'] = sync_api_mod
request = requests = mock_req

# Inject common variable names found in LLM hallucinations
payment_gateway = auth_service = inventory = billing = notification = db = MagicMock()
"""
                    f.write(mock_setup + "\n\n")
                    
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
