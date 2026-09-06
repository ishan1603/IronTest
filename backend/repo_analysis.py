"""Understands a repository well enough to write tests against its real code.

Two jobs. detect_stack reads the manifest files to work out what language and
test runner the project uses, which the runner needs to install and invoke the
right toolchain. build_code_context picks the source files most relevant to a
requirement and extracts their public symbols, so generated tests import real
functions instead of inventing a shape that does not exist.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import github_client

logger = logging.getLogger(__name__)

# Reading source costs a GitHub call each, so cap both count and size.
MAX_CONTEXT_FILES = 12
MAX_FILE_BYTES = 60_000
MAX_EXCERPT_CHARS = 4_000

SOURCE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".rs": "rust",
    ".php": "php",
}

IGNORED_PATH_PARTS = (
    "node_modules/", ".venv/", "venv/", "dist/", "build/", ".next/", "vendor/",
    "__pycache__/", ".git/", "site-packages/", "coverage/", ".mypy_cache/",
    "migrations/", "fixtures/", ".min.js",
)

TEST_PATH_HINTS = ("test_", "_test.", "/tests/", "/test/", ".test.", ".spec.", "spec/")

# Words that carry no signal when matching a requirement to source files.
STOPWORDS = frozenset(
    """a an and are as at be but by for from has have if in into is it its of on or
    should that the then there these they this to was were when will with would user
    users able want need needs make sure system feature add adds added support"""
    .split()
)


@dataclass
class StackProfile:
    language: str = "unknown"
    test_framework: str = ""
    package_manager: str = ""
    install_command: str = ""
    test_command: str = ""
    source_dirs: list[str] = field(default_factory=list)
    test_dirs: list[str] = field(default_factory=list)
    has_tests: bool = False
    manifest_files: list[str] = field(default_factory=list)
    #: "esm" when the generated suite may use import syntax, else "cjs".
    module_system: str = "cjs"
    #: The repo defines scripts.test, so its own runner config applies.
    has_test_script: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "test_framework": self.test_framework,
            "package_manager": self.package_manager,
            "install_command": self.install_command,
            "test_command": self.test_command,
            "source_dirs": self.source_dirs,
            "test_dirs": self.test_dirs,
            "has_tests": self.has_tests,
            "manifest_files": self.manifest_files,
            "module_system": self.module_system,
            "has_test_script": self.has_test_script,
        }


def _is_ignored(path: str) -> bool:
    lowered = path.lower()
    return any(part in lowered for part in IGNORED_PATH_PARTS)


def _is_test_path(path: str) -> bool:
    lowered = path.lower()
    return any(hint in lowered for hint in TEST_PATH_HINTS)


def _top_dirs(paths: list[str]) -> list[str]:
    """Most common first path segments, as a proxy for source roots."""
    counts: dict[str, int] = {}
    for path in paths:
        head = path.split("/")[0]
        if "." not in head:
            counts[head] = counts.get(head, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]]


def _detect_python(files: set[str], contents: dict[str, str]) -> StackProfile:
    profile = StackProfile(language="python", test_framework="pytest", package_manager="pip")
    profile.test_command = "pytest -q --junitxml=results.xml"

    if "pyproject.toml" in files:
        profile.manifest_files.append("pyproject.toml")
        body = contents.get("pyproject.toml", "")
        if "[tool.poetry]" in body:
            profile.package_manager = "poetry"
            profile.install_command = "poetry install --no-interaction"
        else:
            profile.install_command = "pip install -e . || pip install ."
        if "unittest" in body and "pytest" not in body:
            profile.test_framework = "unittest"
            profile.test_command = "python -m unittest discover"
    if "requirements.txt" in files:
        profile.manifest_files.append("requirements.txt")
        # Explicit requirements are the most reliable install path.
        profile.install_command = "pip install -r requirements.txt"

    if not profile.install_command:
        profile.install_command = "pip install pytest"
    return profile


def _detect_node(files: set[str], contents: dict[str, str]) -> StackProfile:
    profile = StackProfile(language="javascript", package_manager="npm")
    profile.manifest_files.append("package.json")

    if "pnpm-lock.yaml" in files:
        profile.package_manager, profile.install_command = "pnpm", "pnpm install --frozen-lockfile"
    elif "yarn.lock" in files:
        profile.package_manager, profile.install_command = "yarn", "yarn install --frozen-lockfile"
    elif "package-lock.json" in files:
        profile.install_command = "npm ci"
    else:
        profile.install_command = "npm install"

    try:
        manifest = json.loads(contents.get("package.json", "{}"))
    except json.JSONDecodeError:
        manifest = {}

    deps = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    if "vitest" in deps:
        profile.test_framework = "vitest"
        profile.test_command = "npx vitest run --reporter=junit --outputFile=results.xml"
    elif "jest" in deps:
        profile.test_framework = "jest"
        profile.test_command = "npx jest --ci --reporters=default --reporters=jest-junit"
    elif "mocha" in deps:
        profile.test_framework = "mocha"
        profile.test_command = "npx mocha --reporter xunit --reporter-option output=results.xml"
    elif manifest.get("scripts", {}).get("test"):
        profile.test_framework = "npm-script"
        profile.test_command = "npm test"

    if any(key in deps for key in ("typescript", "@types/node")) or "tsconfig.json" in files:
        profile.language = "typescript"

    profile.has_test_script = bool(manifest.get("scripts", {}).get("test"))

    # Generated tests may only use import syntax when something will transform
    # them: an explicit ESM package, a babel/jest/next config, or ts-jest.
    has_transform = bool(
        files
        & {
            "jest.config.js", "jest.config.ts", "jest.config.mjs", "jest.config.cjs",
            "babel.config.js", "babel.config.json", ".babelrc", ".babelrc.js",
            "vitest.config.ts", "vitest.config.js",
        }
    )
    is_esm_package = manifest.get("type") == "module"
    profile.module_system = "esm" if (is_esm_package or has_transform or "vitest" in deps) else "cjs"
    return profile


def detect_stack(tree: list[dict[str, Any]], contents: dict[str, str] | None = None) -> StackProfile:
    """Infer language, test runner, and commands from the file tree.

    contents may carry already-fetched manifest bodies; anything missing is
    simply treated as absent rather than fetched here.
    """
    contents = contents or {}
    paths = [item["path"] for item in tree if item.get("type") == "blob" and not _is_ignored(item["path"])]
    files = set(paths)

    if "package.json" in files:
        profile = _detect_node(files, contents)
    elif files & {"pyproject.toml", "requirements.txt", "setup.py", "Pipfile"}:
        profile = _detect_python(files, contents)
    elif "go.mod" in files:
        profile = StackProfile(
            language="go",
            test_framework="go test",
            package_manager="go",
            install_command="go mod download",
            test_command="go test ./... -v",
            manifest_files=["go.mod"],
        )
    elif "Cargo.toml" in files:
        profile = StackProfile(
            language="rust",
            test_framework="cargo test",
            package_manager="cargo",
            install_command="cargo fetch",
            test_command="cargo test",
            manifest_files=["Cargo.toml"],
        )
    elif "Gemfile" in files:
        profile = StackProfile(
            language="ruby",
            test_framework="rspec",
            package_manager="bundler",
            install_command="bundle install",
            test_command="bundle exec rspec",
            manifest_files=["Gemfile"],
        )
    else:
        # No manifest: fall back to whichever source extension dominates.
        counts: dict[str, int] = {}
        for path in paths:
            for ext, lang in SOURCE_EXTENSIONS.items():
                if path.endswith(ext):
                    counts[lang] = counts.get(lang, 0) + 1
        language = max(counts, key=counts.get) if counts else "unknown"
        profile = StackProfile(language=language)
        if language == "python":
            profile.test_framework = "pytest"
            profile.install_command = "pip install pytest"
            profile.test_command = "pytest -q --junitxml=results.xml"

    test_paths = [path for path in paths if _is_test_path(path)]
    profile.has_tests = bool(test_paths)
    profile.test_dirs = sorted({path.rsplit("/", 1)[0] for path in test_paths if "/" in path})[:8]
    profile.source_dirs = _top_dirs([p for p in paths if not _is_test_path(p)])
    return profile


# -- symbol extraction -----------------------------------------------------


def _python_symbols(source: str) -> list[dict[str, Any]]:
    """Top-level public functions and classes, with signatures."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    symbols: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            symbols.append(
                {
                    "kind": "function",
                    "name": node.name,
                    "signature": f"{node.name}({', '.join(a.arg for a in node.args.args)})",
                    "doc": (ast.get_docstring(node) or "").split("\n")[0][:160],
                }
            )
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            methods = [
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_")
            ]
            symbols.append(
                {
                    "kind": "class",
                    "name": node.name,
                    "signature": f"class {node.name}",
                    "methods": methods[:12],
                    "doc": (ast.get_docstring(node) or "").split("\n")[0][:160],
                }
            )
    return symbols


_JS_EXPORT = re.compile(
    r"^export\s+(?:default\s+)?(?:async\s+)?(function|class|const|let|var)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


def _js_symbols(source: str) -> list[dict[str, Any]]:
    return [
        {"kind": "class" if kind == "class" else "function", "name": name, "signature": name}
        for kind, name in _JS_EXPORT.findall(source)
    ]


def extract_symbols(path: str, source: str) -> list[dict[str, Any]]:
    if path.endswith(".py"):
        return _python_symbols(source)
    if any(path.endswith(ext) for ext in (".js", ".jsx", ".ts", ".tsx")):
        return _js_symbols(source)
    return []


# -- relevance -------------------------------------------------------------


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9_]{2,}", text.lower())
    return {word for word in words if word not in STOPWORDS}


def rank_files(tree: list[dict[str, Any]], requirement: str, *, limit: int = MAX_CONTEXT_FILES) -> list[str]:
    """Source files most likely to be relevant to a requirement.

    Scores on filename and path-segment overlap with the requirement's
    keywords. Crude, but it beats sending an arbitrary slice of the repo, and
    it degrades to "largest source files" when nothing matches.
    """
    terms = _keywords(requirement)
    candidates: list[tuple[float, int, str]] = []

    for item in tree:
        path = item.get("path", "")
        if item.get("type") != "blob" or _is_ignored(path) or _is_test_path(path):
            continue
        if not any(path.endswith(ext) for ext in SOURCE_EXTENSIONS):
            continue
        size = int(item.get("size") or 0)
        if size == 0 or size > MAX_FILE_BYTES:
            continue

        segments = _keywords(path.replace("/", " ").replace("_", " ").replace("-", " "))
        overlap = len(terms & segments)
        # Prefer a filename hit over a directory hit.
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        score = overlap * 2.0 + (3.0 if _keywords(stem) & terms else 0.0)
        candidates.append((score, size, path))

    scored = [c for c in candidates if c[0] > 0]
    if scored:
        scored.sort(key=lambda c: (-c[0], -c[1]))
        return [path for _, _, path in scored[:limit]]

    # Nothing matched: fall back to the largest source files, which are the
    # most likely to hold the core logic.
    candidates.sort(key=lambda c: -c[1])
    return [path for _, _, path in candidates[:limit]]


async def build_code_context(
    token: str,
    full_name: str,
    ref: str,
    requirement: str,
    *,
    tree: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stack profile plus relevant source excerpts and their public symbols."""
    if tree is None:
        tree = await github_client.fetch_repo_tree(token, full_name, ref)

    manifest_names = (
        "package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml", "Gemfile",
    )
    present = {item["path"] for item in tree if item.get("type") == "blob"}
    manifests: dict[str, str] = {}
    for name in manifest_names:
        if name in present:
            try:
                manifests[name] = await github_client.fetch_file(token, full_name, name, ref)
            except github_client.GitHubError:
                logger.debug("Could not read manifest %s in %s", name, full_name)

    profile = detect_stack(tree, manifests)
    selected = rank_files(tree, requirement)

    files: list[dict[str, Any]] = []
    for path in selected:
        try:
            source = await github_client.fetch_file(token, full_name, path, ref)
        except github_client.GitHubError:
            continue
        if not source.strip():
            continue
        files.append(
            {
                "path": path,
                "symbols": extract_symbols(path, source),
                "excerpt": source[:MAX_EXCERPT_CHARS],
                "truncated": len(source) > MAX_EXCERPT_CHARS,
            }
        )

    existing_tests = [
        item["path"] for item in tree
        if item.get("type") == "blob" and _is_test_path(item["path"]) and not _is_ignored(item["path"])
    ][:20]

    return {
        "repository": full_name,
        "ref": ref,
        "stack": profile.to_dict(),
        "files": files,
        "existing_tests": existing_tests,
        "file_count": len([i for i in tree if i.get("type") == "blob"]),
    }
