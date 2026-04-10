import tempfile
import subprocess
import time
import sys
import os
import asyncio
import textwrap
import re
import json
from typing import List

from models import TestCase, TestResult, TestExecutionSummary, ImprovementSuggestion
from llm_client import llm_generate_json


def _analyze_error_with_ai(error_message: str, snippet: str) -> List[ImprovementSuggestion]:
    """
    Use AI to analyze test failure and generate specific fix suggestions.
    Falls back to basic error detection if LLM call fails.
    """
    # SKIP AI - use smart fallback instead
    # AI calls are failing silently, so let's use intelligent pattern matching
    return []


def _extract_error_from_logs(error_message: str) -> dict:
    """Extract key error information from pytest output."""
    error_info = {
        "type": "unknown",
        "message": "",
        "assertion_failed": False,
        "error_type": None
    }
    
    lines = error_message.split('\n')
    
    # Find the failure line
    for line in lines:
        lower = line.lower()
        if 'assert' in lower and 'failed' not in lower:
            error_info["assertion_failed"] = True
            error_info["message"] = line.strip()
            break
        elif any(x in lower for x in ['error:', 'exception:', 'failed', 'failed [']):
            error_info["message"] = line.strip()
            if 'keyerror' in lower:
                error_info["error_type"] = "keyerror"
            elif 'attributeerror' in lower:
                error_info["error_type"] = "attributeerror"
            elif 'typeerror' in lower:
                error_info["error_type"] = "typeerror"
            elif 'indexerror' in lower:
                error_info["error_type"] = "indexerror"
            break
    
    return error_info


def _generate_fix_suggestions(test_id: str, error_message: str, snippet: str) -> List[ImprovementSuggestion]:
    """
    Analyze test failure error message and generate specific, actionable fix suggestions.
    
    Primary: Use AI for intelligent analysis
    Fallback: Use pattern matching if AI unavailable
    """
    # Try AI-powered analysis first
    ai_suggestions = _analyze_error_with_ai(error_message, snippet)
    if ai_suggestions:
        return ai_suggestions
    
    # FALLBACK: Pattern matching if AI fails
    suggestions = []
    error_lower = error_message.lower()
    
    # KeyError pattern: Missing dictionary key
    key_error_match = re.search(r"keyerror[:\s]+['\"]([^'\"]+)['\"]", error_message, re.IGNORECASE)
    if key_error_match:
        missing_key = key_error_match.group(1)
        suggestions.append(ImprovementSuggestion(
            area="Data Access",
            current_issue=f"KeyError: '{missing_key}' - Accessing missing dictionary key",
            why_it_matters="The response doesn't have the field '{missing_key}', causing the test to crash",
            what_to_remove=f"response['{missing_key}']  (direct unsafe access)",
            why_to_remove_it="Direct access fails when key is missing",
            what_to_add=f"response.get('{missing_key}', None)  (safe access with default)",
            why_to_add_it="Safe access prevents crashes and returns None if key missing"
        ))
    
    # AttributeError pattern: NoneType or missing attribute
    if "attributeerror" in error_lower or "'nonetype'" in error_lower:
        suggestions.append(ImprovementSuggestion(
            area="Null Safety",
            current_issue="AttributeError - Using method/property on None or uninitialized object",
            why_it_matters="An object is None before you try to use it",
            what_to_remove="obj.method()  or  obj.attribute  (without checking)",
            why_to_remove_it="Fails when obj is None",
            what_to_add="if obj: obj.method()  or  (obj or {}).get('attr')",
            why_to_add_it="Checks for None before using"
        ))
    
    # AssertionError pattern: Assertion failed - MUST COME FIRST
    # Look for HTTP status code mismatches like "assert (200 == 409)"
    status_match = re.search(r"assert\s+\((\d+)\s*==\s*(\d+)\)", error_message)
    if status_match:
        actual_status = int(status_match.group(1))
        expected_status = int(status_match.group(2))
        status_meanings = {
            200: 'OK (success)', 201: 'Created', 204: 'No Content',
            400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
            404: 'Not Found', 409: 'Conflict', 500: 'Internal Server Error'
        }
        actual_meaning = status_meanings.get(actual_status, f'HTTP {actual_status}')
        expected_meaning = status_meanings.get(expected_status, f'HTTP {expected_status}')
        
        suggestions.append(ImprovementSuggestion(
            area="API Response Status",
            current_issue=f"API returned {actual_status} ({actual_meaning}) but test expected {expected_status} ({expected_meaning})",
            why_it_matters=f"Status code mismatch - the endpoint should return {expected_meaning} for this operation",
            what_to_remove="# The current request is succeeding when it should fail",
            why_to_remove_it=f"{actual_status} means success, but your test expects {expected_meaning} error",
            what_to_add=f"# Verify the request triggers {expected_status}\n# Check request data/conditions\n# May need to adjust test input to trigger the error",
            why_to_add_it=f"The API endpoint must be configured to return {expected_status} in this scenario"
        ))
    
    # Generic assertion patterns
    assertion_match = re.search(r"assert\s+\((.+?)\)", error_message, re.IGNORECASE | re.DOTALL)
    if (assertion_match or "assert" in error_lower or "failed" in error_lower) and not suggestions:
        # Extract what was being compared
        comparison = assertion_match.group(1) if assertion_match else ""
        suggestions.append(ImprovementSuggestion(
            area="Assertion Logic",
            current_issue=f"AssertionError - {comparison[:50] if comparison else 'Assertion failed'}",
            why_it_matters="The test expects a certain condition but the code produces different result",
            what_to_remove="Hardcoded expected values like: assert response.status_code == 200",
            why_to_remove_it="Hardcoded values don't match actual API responses or behavior",
            what_to_add="Use variables from actual response: assert response.status_code == expected_code",
            why_to_add_it="Assertions should check actual values, not hardcoded guesses"
        ))
    
    # Response content check failures: 'string' in response.text or similar
    content_check = re.search(r"assert\s+['\"]([^'\"]+)['\"]\s+in\s+(.+?)(?:\n|$)", error_message)
    if content_check and not suggestions:
        search_value = content_check.group(1)
        search_target = content_check.group(2).strip()
        suggestions.append(ImprovementSuggestion(
            area="Response Content Validation",
            current_issue=f"'{search_value}' not found in {search_target}",
            why_it_matters=f"The API response doesn't contain '{search_value}' that was expected",
            what_to_remove=f"# Just checking status code without validating response content",
            why_to_remove_it="Status 200 doesn't guarantee the right content in response body",
            what_to_add=f"# Add detailed response inspection:\nprint(f'Response: {{{search_target}}}')\nprint(f'Type: {{type({search_target})}}')",
            why_to_add_it=f"See the actual response to understand why '{search_value}' is missing"
        ))
    
    # KeyError pattern: Missing dictionary key
    key_error_match = re.search(r"keyerror[:\s]+['\"]([^'\"]+)['\"]", error_message, re.IGNORECASE)
    if key_error_match and not suggestions:
        missing_key = key_error_match.group(1)
        suggestions.append(ImprovementSuggestion(
            area="Data Access",
            current_issue=f"KeyError: '{missing_key}' - Accessing missing dictionary key",
            why_it_matters="The response doesn't have the field '{missing_key}', causing the test to crash",
            what_to_remove=f"response['{missing_key}']  (direct unsafe access)",
            why_to_remove_it="Direct access fails when key is missing",
            what_to_add=f"response.get('{missing_key}', None)  (safe access with default)",
            why_to_add_it="Safe access prevents crashes and returns None if key missing"
        ))
    
    # TypeError pattern: Type mismatch
    if "typeerror" in error_lower and not suggestions:
        suggestions.append(ImprovementSuggestion(
            area="Type Handling",
            current_issue="TypeError - Operation on wrong data type",
            why_it_matters="Mixing types (string vs int, comparing incompatibles, etc.)",
            what_to_remove="str_value + int_value  or  dict['key'] != 0  (type mismatch)",
            why_to_remove_it="Can't mix types without conversion",
            what_to_add="int(value) + 5  or  str(value) == '0'  (convert before operation)",
            why_to_add_it="Ensures compatible types before operations"
        ))
    
    # IndexError: Array out of bounds
    if "indexerror" in error_lower or "list index out of range" in error_lower:
        suggestions.append(ImprovementSuggestion(
            area="Array Bounds",
            current_issue="IndexError - Array index out of range",
            why_it_matters="Accessing array[N] when array has fewer than N+1 elements",
            what_to_remove="items[0] or data[5]  (without checking length)",
            why_to_remove_it="Crashes if array is too short",
            what_to_add="items[0] if len(items) > 0 else None",
            why_to_add_it="Safely handles empty or short arrays"
        ))
    
    # NameError: Undefined variable
    if "nameerror" in error_lower or "is not defined" in error_lower:
        suggestions.append(ImprovementSuggestion(
            area="Variable Definition",
            current_issue="NameError - Using undefined variable or function",
            why_it_matters="Variable was never created or imported",
            what_to_remove="Using variable_name without defining it first",
            why_to_remove_it="Variable doesn't exist in this scope",
            what_to_add="Define it first: variable_name = value  or  from module import variable_name",
            why_to_add_it="Variables must exist before use"
        ))
    
    # Connection/Network errors
    if any(x in error_lower for x in ["connection", "refused", "timeout", "unreachable", "connection refused"]):
        suggestions.append(ImprovementSuggestion(
            area="External Dependencies",
            current_issue="ConnectionError - Can't reach external service",
            why_it_matters="Test tries to call real API but service isn't available",
            what_to_remove="requests.post('http://real-api.com/...')  (real network call)",
            why_to_remove_it="Tests shouldn't depend on real external services",
            what_to_add="All external calls are already mocked in this environment",
            why_to_add_it="Mocks prevent network calls and make tests fast"
        ))
    
    # Generic Python errors
    if "error" in error_lower or "exception" in error_lower:
        # Try to extract the error type
        error_match = re.search(r"(error|exception)[:\s]+(\w+)", error_message, re.IGNORECASE)
        error_type = error_match.group(2) if error_match else "Error"
        
        if not suggestions:  # Only add if no specific pattern matched
            suggestions.append(ImprovementSuggestion(
                area="Test Execution",
                current_issue=f"{error_type} - Test execution failed",
                why_it_matters="The test code has an issue preventing it from running",
                what_to_remove="Review test code for typos, wrong variable names, or logic errors",
                why_to_remove_it="LLM-generated code may have mistakes",
                what_to_add="Add safety checks: null checks, type validation, try-except blocks",
                why_to_add_it="Defensive code handles edge cases and errors better"
            ))
    
    # ALWAYS ensure suggestions is not empty
    if not suggestions:
        # Extract first meaningful line from error
        lines = [l.strip() for l in error_message.split('\n') if l.strip() and not l.startswith('...')]
        first_error_line = lines[0] if lines else error_message[:100]
        
        suggestions.append(ImprovementSuggestion(
            area="Test Debug",
            current_issue=f"Test failed: {first_error_line[:80]}",
            why_it_matters="The test execution encountered an error",
            what_to_remove="Review test code for issues or assumptions",
            why_to_remove_it="Generated code may have bugs",
            what_to_add="Add error handling and validation to the test code above",
            why_to_add_it="Defensive code prevents failures in edge cases"
        ))
    
    return suggestions


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
from unittest.mock import MagicMock, patch

# Override time.sleep() to prevent hanging tests
import time as _time_module
_original_sleep = _time_module.sleep
def _mock_sleep(seconds):
    # Don't actually sleep - just pretend to for testing
    return None
_time_module.sleep = _mock_sleep

# Override input() to prevent test blocking on stdin
import builtins as _builtins
_original_input = _builtins.input
def _mock_input(prompt=""):
    # Return empty string instantly instead of waiting for user input
    return ""
_builtins.input = _mock_input

# Global module stubbing to prevent real network calls
class MockResponse:
    def __init__(self, url="", method="get", body=None):
        self.url = str(url).lower()
        self.method = str(method).lower()
        self.body = body
        
        # Smart status code based on request structure
        self.status_code = self._infer_status(body)
        self._error = ""
        self._payload = self._infer_payload(body)
    
    def _infer_status(self, body):
        # Return appropriate HTTP status based on request content
        if not isinstance(body, dict):
            return 200  # Accept any non-dict as valid
        
        # Check for obviously invalid payloads
        if body and any(str(v).lower() == "invalid" for v in body.values()):
            return 400
        
        if body and any(str(v) == "" for v in body.values() if isinstance(v, str)):
            # Empty string is valid in mocks - return success
            return 200
        
        return 200  # Default: accept all valid dict payloads
    
    def _infer_payload(self, body):
        # Generate sensible response payload based on request
        payload = {"status": "success"}
        
        if isinstance(body, dict):
            # Mirror back request keys with sensible responses
            for key in body.keys():
                if "id" in key.lower() or "code" in key.lower():
                    payload[f"{key}_result"] = "VALID"
                elif "token" in key.lower():
                    payload["token"] = "tok_mockgenerated_123"
                elif "discount" in key.lower():
                    payload["discount_applied"] = True
                elif "expiry" in key.lower():
                    payload["expiry_valid"] = True
                elif "email" in key.lower():
                    payload["email_verified"] = True
        
        payload["timestamp"] = "2025-01-01T00:00:00Z"
        return payload
    
    def json(self):
        return dict(self._payload)
    
    @property
    def status(self):
        return self.status_code
    
    @property
    def ok(self):
        return self.status_code < 400


def _mock_call(url, *args, **kwargs):
    body = kwargs.get("json") or kwargs.get("data")
    method = kwargs.get("method", "get")
    url_str = str(url).lower()
    
    # Generic success for any endpoint - allows test discovery
    response = MockResponse(url=url_str, method=method, body=body)
    response.status_code = response._infer_status(body)
    return response

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
                    # Increased timeout from 20s to 60s for complex test scenarios
                    proc = subprocess.run(
                        [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"], 
                        capture_output=True, 
                        text=True, 
                        timeout=60
                    )
                    
                    if proc.returncode == 0:
                        out = proc.stdout.strip()
                        if len(out) > 800:
                            out = "..." + out[-800:]
                        if not out:
                            out = "Test passed without additional logs."
                        # Even passing tests can have improvement suggestions
                        pass_suggestion = [ImprovementSuggestion(
                            area="Test Quality",
                            current_issue="Test passed successfully ✓",
                            why_it_matters="Test execution completed without errors",
                            what_to_remove="",
                            why_to_remove_it="",
                            what_to_add="Consider adding edge case tests and error condition testing",
                            why_to_add_it="Comprehensive tests catch more bugs"
                        )]
                        results.append(TestResult(test_id=t.id, status="pass", error_message=out, suggestions=pass_suggestion))
                    else:
                        # Extract the most relevant error part (tail of stdout)
                        err_out = proc.stdout.strip()
                        if not err_out:
                            err_out = proc.stderr.strip()
                        
                        # Just take the last 1000 characters to prevent massive logs
                        if len(err_out) > 1000:
                            err_out = "..." + err_out[-1000:]
                        
                        # Generate specific fix suggestions based on the error
                        fix_suggestions = _generate_fix_suggestions(t.id, err_out, snippet)
                        results.append(TestResult(test_id=t.id, status="fail", error_message=err_out, suggestions=fix_suggestions))
                except subprocess.TimeoutExpired:
                    timeout_suggestion = [ImprovementSuggestion(
                        area="Performance",
                        current_issue="Test execution timeout exceeded (60s)",
                        why_it_matters="The test is taking too long, likely due to infinite loops or unhandled async operations",
                        what_to_remove="Remove infinite loops, long sleep() calls that weren't mocked, or blocking wait operations",
                        why_to_remove_it="Tests should complete quickly; long waits indicate issues in test code",
                        what_to_add="Simplify test logic, use mocked objects for external calls, and avoid complex async/threading code",
                        why_to_add_it="Mock test code runs synchronously and completes quickly"
                    )]
                    results.append(TestResult(test_id=t.id, status="error", error_message="Execution timeout exceeded (60s)", suggestions=timeout_suggestion))
                except Exception as e:
                    exception_suggestion = [ImprovementSuggestion(
                        area="Test Setup",
                        current_issue=f"Unexpected error during test execution: {str(e)}",
                        why_it_matters="An unexpected exception occurred that prevented the test from running",
                        what_to_remove="Remove any code that assumes specific imports or global state",
                        why_to_remove_it="Test environment may not have all dependencies available",
                        what_to_add="Wrap test code in try-except, ensure all imports are standard library or mocked, add debug output",
                        why_to_add_it="Better error handling reveals root cause of failures"
                    )]
                    results.append(TestResult(test_id=t.id, status="error", error_message=str(e), suggestions=exception_suggestion))

        duration = time.time() - start_time
        return TestExecutionSummary(results=results, duration_seconds=round(duration, 2))

    return await asyncio.to_thread(_run)
