"""Assembling generated cases into a runnable file.

The generated function name carries the case id, and the runner's JUnit report
is parsed back through that same id. If the two ever disagree, results stop
mapping to the requirements that produced them.
"""

import subprocess
import sys

from agents.suite_builder import build_suite, function_name
from models import TestCase
from runners.base import parse_junit


def case(case_id="TC-001", description="applies the discount", body=None, automated=True):
    return TestCase(
        id=case_id,
        type="functional",
        module="billing",
        description=description,
        expected_result="10% off",
        risk_level="medium",
        automated=automated,
        automation_snippet=body if body is not None else ["assert 1 + 1 == 2"],
    )


def test_function_name_embeds_the_case_id():
    assert function_name(case("TC-007", "handles empty cart")).startswith("test_TC_007_")


def test_builds_a_python_file_with_imports_and_one_function_per_case():
    files = build_suite(
        [case("TC-001", "first"), case("TC-002", "second")],
        ["from app.billing import apply_discount"],
        language="python",
    )

    assert len(files) == 1
    assert files[0].path == "tests/test_irontest_generated.py"
    content = files[0].content
    assert "from app.billing import apply_discount" in content
    assert "def test_TC_001_first():" in content
    assert "def test_TC_002_second():" in content


def test_duplicate_imports_are_emitted_once():
    files = build_suite(
        [case()],
        ["from app import x", "from app import x", "from app import y"],
        language="python",
    )
    assert files[0].content.count("from app import x") == 1


def test_snippet_is_reindented_and_a_stray_def_line_is_dropped():
    """Models emit bodies with and without their own def line."""
    files = build_suite(
        [case(body=["def test_whatever():", "        assert True"])],
        [],
        language="python",
    )
    content = files[0].content

    assert content.count("def test_") == 1
    assert "    assert True" in content


def test_cases_without_a_runnable_snippet_are_omitted():
    files = build_suite(
        [case("TC-001"), case("TC-002", automated=False, body=[])],
        [],
        language="python",
    )
    content = files[0].content
    assert "TC_001" in content
    assert "TC_002" not in content


def test_no_runnable_cases_produces_no_file():
    assert build_suite([case(automated=False, body=[])], [], language="python") == []


def test_javascript_suite_uses_test_blocks():
    files = build_suite(
        [case("TC-001", "adds tax")],
        ["import { addTax } from '../src/tax';"],
        language="javascript",
        module_system="esm",
    )

    assert files[0].path.endswith(".test.js")
    assert "import { addTax }" in files[0].content
    assert "test('test_TC_001_adds_tax'" in files[0].content


def test_generated_python_suite_actually_runs_and_maps_back_to_case_ids(tmp_path):
    """End-to-end: build a suite, run pytest on it, parse results by case id."""
    cases = [
        case("TC-001", "passes", ["assert sum([1, 2, 3]) == 6"]),
        case("TC-002", "fails", ["assert sum([1, 2, 3]) == 7"]),
    ]
    files = build_suite(cases, [], language="python")

    suite_path = tmp_path / "test_generated.py"
    suite_path.write_text(files[0].content, encoding="utf-8")
    report = tmp_path / "results.xml"

    subprocess.run(
        [sys.executable, "-m", "pytest", str(suite_path), f"--junitxml={report}", "-q"],
        capture_output=True,
        cwd=tmp_path,
    )

    results = {r.test_id: r.status for r in parse_junit(report.read_text(encoding="utf-8"))}
    assert results == {"TC-001": "pass", "TC-002": "fail"}


# -- JS / TS module system ---------------------------------------------------


def js_case(case_id="TC-001", description="adds tax", body=None):
    return TestCase(
        id=case_id,
        type="functional",
        module="cart",
        description=description,
        expected_result="ok",
        risk_level="low",
        automated=True,
        automation_snippet=body or ["expect(1 + 1).toBe(2);"],
    )


IMPORTS = [
    "import { applyDiscount } from '../src/pricing';",
    'import Cart from "../src/cart";',
    "import * as utils from './utils';",
]


def test_esm_imports_become_require_without_a_transform():
    """Jest with no transform runs files as CommonJS; an import dies at load."""
    files = build_suite([js_case()], IMPORTS, language="typescript", module_system="cjs")
    content = files[0].content

    assert "import {" not in content
    assert "const {applyDiscount} = require('../src/pricing');" in content
    assert "const Cart = require('../src/cart');" in content
    assert "const utils = require('./utils');" in content


def test_esm_is_preserved_when_the_repo_has_a_transform():
    files = build_suite([js_case()], IMPORTS, language="typescript", module_system="esm")
    content = files[0].content

    assert "import { applyDiscount } from '../src/pricing';" in content
    assert "require(" not in content


def test_typescript_still_writes_a_dot_js_suite():
    """A .ts suite dies at load under a bare jest run, so the file is .js."""
    for language in ("typescript", "javascript"):
        files = build_suite([js_case()], [], language=language)
        assert files[0].path.endswith(".test.js"), language
        assert ".ts" not in files[0].path
