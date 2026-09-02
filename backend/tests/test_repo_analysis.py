"""Stack detection, symbol extraction, and file relevance.

These decide what the runner installs and what the generator can import, so a
wrong answer here produces tests that cannot run against the real code.
"""

import json

from repo_analysis import detect_stack, extract_symbols, rank_files


def tree(*paths, sizes=None):
    sizes = sizes or {}
    return [{"path": p, "type": "blob", "size": sizes.get(p, 1000)} for p in paths]


# -- stack detection -------------------------------------------------------


def test_detects_pytest_project_from_requirements():
    profile = detect_stack(tree("requirements.txt", "app/main.py", "tests/test_main.py"))

    assert profile.language == "python"
    assert profile.test_framework == "pytest"
    assert profile.install_command == "pip install -r requirements.txt"
    assert profile.has_tests is True


def test_detects_poetry_project():
    contents = {"pyproject.toml": "[tool.poetry]\nname = 'x'\n"}
    profile = detect_stack(tree("pyproject.toml", "src/x.py"), contents)

    assert profile.package_manager == "poetry"
    assert "poetry install" in profile.install_command


def test_detects_vitest_over_generic_npm_script():
    contents = {
        "package.json": json.dumps(
            {"scripts": {"test": "vitest"}, "devDependencies": {"vitest": "^1.0.0"}}
        )
    }
    profile = detect_stack(tree("package.json", "package-lock.json", "src/index.js"), contents)

    assert profile.test_framework == "vitest"
    assert profile.install_command == "npm ci"


def test_detects_pnpm_and_typescript():
    contents = {"package.json": json.dumps({"devDependencies": {"jest": "^29", "typescript": "^5"}})}
    profile = detect_stack(tree("package.json", "pnpm-lock.yaml", "tsconfig.json", "src/a.ts"), contents)

    assert profile.package_manager == "pnpm"
    assert profile.language == "typescript"
    assert profile.test_framework == "jest"


def test_detects_go_module():
    profile = detect_stack(tree("go.mod", "main.go", "main_test.go"))

    assert profile.language == "go"
    assert profile.test_command == "go test ./... -v"
    assert profile.has_tests is True


def test_repository_without_tests_is_flagged():
    profile = detect_stack(tree("requirements.txt", "app/main.py"))
    assert profile.has_tests is False


def test_falls_back_to_dominant_extension_without_a_manifest():
    profile = detect_stack(tree("a.py", "b.py", "c.py", "d.js"))
    assert profile.language == "python"


def test_vendor_directories_are_ignored():
    profile = detect_stack(
        tree("node_modules/pkg/package.json", "requirements.txt", "app/main.py")
    )
    # node_modules must not make this look like a Node project.
    assert profile.language == "python"


# -- symbol extraction -----------------------------------------------------


def test_extracts_public_python_symbols_with_signatures():
    source = '''
def apply_discount(total, percent):
    """Apply a percentage discount."""
    return total * (1 - percent / 100)

def _internal_helper(x):
    return x

class PricingEngine:
    """Prices a basket."""
    def quote(self, items): ...
    def _cache_key(self): ...
'''
    symbols = extract_symbols("pricing.py", source)
    by_name = {s["name"]: s for s in symbols}

    assert "apply_discount" in by_name
    assert by_name["apply_discount"]["signature"] == "apply_discount(total, percent)"
    assert by_name["apply_discount"]["doc"] == "Apply a percentage discount."

    # Private names are noise for a test author.
    assert "_internal_helper" not in by_name
    assert by_name["PricingEngine"]["methods"] == ["quote"]


def test_unparseable_python_yields_no_symbols_rather_than_raising():
    assert extract_symbols("broken.py", "def oops(:\n  pass") == []


def test_extracts_javascript_exports():
    source = """
export function applyDiscount(total) { return total; }
export const TAX_RATE = 0.2;
export default class Cart {}
function notExported() {}
"""
    names = {s["name"] for s in extract_symbols("cart.js", source)}
    assert {"applyDiscount", "TAX_RATE", "Cart"} <= names
    assert "notExported" not in names


# -- relevance ranking -----------------------------------------------------


def test_ranks_files_matching_the_requirement_first():
    files = tree(
        "src/billing/discount.py",
        "src/auth/login.py",
        "src/util/logger.py",
    )
    ranked = rank_files(files, "Apply a percentage discount at checkout")
    assert ranked[0] == "src/billing/discount.py"


def test_test_files_are_never_offered_as_source_context():
    files = tree("src/discount.py", "tests/test_discount.py")
    assert rank_files(files, "discount") == ["src/discount.py"]


def test_falls_back_to_largest_files_when_nothing_matches():
    files = tree(
        "src/alpha.py", "src/beta.py",
        sizes={"src/alpha.py": 200, "src/beta.py": 9000},
    )
    ranked = rank_files(files, "zzzz completely unrelated requirement")
    assert ranked[0] == "src/beta.py"


def test_vendored_and_oversized_files_are_excluded():
    files = tree(
        "node_modules/x/index.js",
        "dist/bundle.js",
        "src/app.js",
        "src/huge.js",
        sizes={"src/huge.js": 5_000_000},
    )
    ranked = rank_files(files, "app")
    assert ranked == ["src/app.js"]
