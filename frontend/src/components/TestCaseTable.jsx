import React, { useMemo, useState } from "react";
import clsx from "clsx";

const typeLabels = {
  all: "All",
  functional: "Functional",
  boundary: "Boundary",
  edge_case: "Edge",
  regression: "Regression",
};

const riskColors = {
  low: "bg-success/10 dark:bg-success/20 text-emerald-700 dark:text-success",
  medium:
    "bg-amber-100 dark:bg-amber-400/10 text-amber-700 dark:text-amber-300",
  high: "bg-danger/10 text-red-700 dark:text-danger",
};

const statusColors = {
  pass: "text-success bg-success/10",
  fail: "text-danger bg-danger/10",
  error: "text-amber-500 bg-amber-500/10",
  skipped: "text-gray-400 bg-gray-400/10",
};

function buildFailureGuidance(test, result) {
  if (!result || (result.status !== "fail" && result.status !== "error")) {
    return null;
  }

  const message = String(result.error_message || "");
  const normalized = message.toLowerCase();

  let reason =
    "The test did not behave as expected, which means the current implementation and the expected behavior are out of sync.";
  let suggestions = [
    "Re-run this test with verbose logs and compare expected vs actual output step by step.",
    "Validate the test data setup and environment assumptions before execution starts.",
  ];

  if (normalized.includes("timeout") || normalized.includes("timed out")) {
    reason =
      "The test likely failed because the system response took too long, so the assertion window expired before completion.";
    suggestions = [
      "Check slow API/database calls in this flow and optimize the bottleneck.",
      "Increase timeout only after confirming performance is acceptable under normal load.",
      "Add retries for unstable downstream dependencies where appropriate.",
    ];
  } else if (
    normalized.includes("assert") ||
    normalized.includes("expected") ||
    normalized.includes("actual")
  ) {
    reason =
      "The test reached validation, but the actual result did not match the expected business behavior.";
    suggestions = [
      "Compare expected_result with the real payload and update logic or assertion accordingly.",
      "Verify edge-case handling for this module before final assertion is executed.",
      "Add explicit intermediate assertions to pinpoint where divergence starts.",
    ];
  } else if (
    normalized.includes("401") ||
    normalized.includes("403") ||
    normalized.includes("unauthorized") ||
    normalized.includes("forbidden")
  ) {
    reason =
      "The request was blocked by authentication or authorization checks, so the test could not complete the intended path.";
    suggestions = [
      "Validate token/session generation and ensure credentials are valid for this scenario.",
      "Check role/permission mapping for the user used by this test.",
      "Confirm protected endpoints are called with the required auth headers.",
    ];
  } else if (normalized.includes("404") || normalized.includes("not found")) {
    reason =
      "The test could not find a required resource or endpoint, which interrupted the expected flow.";
    suggestions = [
      "Verify route names and service URLs for this environment.",
      "Ensure prerequisite records are created before this test executes.",
      "Add setup checks that fail early when required entities are missing.",
    ];
  } else if (
    normalized.includes("500") ||
    normalized.includes("internal server") ||
    normalized.includes("exception")
  ) {
    reason =
      "The backend threw an internal error during execution, so the test failed before reaching expected output.";
    suggestions = [
      "Inspect server logs for stack traces tied to this module and test id.",
      "Add defensive validation around null/invalid inputs in this code path.",
      "Cover this scenario with a focused unit test to prevent recurrence.",
    ];
  } else if (
    normalized.includes("connect") ||
    normalized.includes("econn") ||
    normalized.includes("network") ||
    normalized.includes("dns") ||
    normalized.includes("socket")
  ) {
    reason =
      "The test failed due to a connectivity issue, so dependent services were not reachable at runtime.";
    suggestions = [
      "Validate service availability and host/port configuration for this environment.",
      "Check firewall/network rules and container-to-container routing.",
      "Introduce health checks before running dependent integration tests.",
    ];
  } else if (
    normalized.includes("json") ||
    normalized.includes("schema") ||
    normalized.includes("validation") ||
    normalized.includes("type")
  ) {
    reason =
      "The response or request format did not match the expected schema, causing validation to fail.";
    suggestions = [
      "Compare the contract/schema with the payload produced during test execution.",
      "Normalize field types and required keys before assertion.",
      "Add schema validation in pre-checks so format errors fail earlier and clearly.",
    ];
  }

  return {
    reason,
    suggestions,
    context: `${test.id} (${test.module})`,
  };
}

export default function TestCaseTable({
  tests = [],
  execution = [],
  criticalIds = [],
}) {
  const [typeFilter, setTypeFilter] = useState("all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [expandedRow, setExpandedRow] = useState(null);
  const [copiedSnippetId, setCopiedSnippetId] = useState("");

  const executionById = useMemo(() => {
    const index = new Map();
    for (const item of execution) {
      index.set(item.test_id, item);
    }
    return index;
  }, [execution]);

  const handleCopySnippet = async (snippet, testId) => {
    const content = Array.isArray(snippet)
      ? snippet.join("\n")
      : String(snippet || "");
    if (!content.trim()) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopiedSnippetId(testId);
      setTimeout(() => setCopiedSnippetId(""), 1200);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopiedSnippetId(testId);
      setTimeout(() => setCopiedSnippetId(""), 1200);
    }
  };

  const filtered = useMemo(() => {
    return tests.filter((t) => {
      const typeOk = typeFilter === "all" || t.type === typeFilter;
      const riskOk = riskFilter === "all" || t.risk_level === riskFilter;
      return typeOk && riskOk;
    });
  }, [tests, typeFilter, riskFilter]);

  return (
    <div className="rounded-3xl border border-black/5 dark:border-white/10 bg-white/60 dark:bg-white/5 p-8 shadow-2xl backdrop-blur-3xl transition-colors duration-300">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold tracking-tight text-gray-900 dark:text-white">
            Test Vector Registry
          </h3>
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mt-1">
            {tests.length} Generated Vectors
          </p>
        </div>
        <div className="flex flex-wrap gap-3 text-xs font-semibold">
          <div className="flex gap-1 p-1 rounded-xl bg-gray-100 dark:bg-black/40 border border-black/5 dark:border-white/5">
            {Object.entries(typeLabels).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setTypeFilter(value)}
                className={clsx(
                  "rounded-lg px-4 py-2 transition-all",
                  typeFilter === value
                    ? "bg-white dark:bg-white/10 text-gray-900 dark:text-white shadow-sm"
                    : "text-gray-500 hover:text-gray-900 dark:hover:text-gray-200",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex gap-1 p-1 rounded-xl bg-gray-100 dark:bg-black/40 border border-black/5 dark:border-white/5">
            {[
              ["all", "All Risks"],
              ["low", "Low"],
              ["medium", "Medium"],
              ["high", "High"],
            ].map(([value, label]) => (
              <button
                key={value}
                onClick={() => setRiskFilter(value)}
                className={clsx(
                  "rounded-lg px-4 py-2 transition-all",
                  riskFilter === value
                    ? "bg-white dark:bg-white/10 text-gray-900 dark:text-white shadow-sm"
                    : "text-gray-500 hover:text-gray-900 dark:hover:text-gray-200",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-black/5 dark:border-white/10 bg-white dark:bg-black/20 shadow-inner">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 dark:bg-white/5 text-gray-500 dark:text-gray-400 text-xs uppercase tracking-widest border-b border-black/5 dark:border-white/10">
            <tr>
              <th className="px-6 py-4 text-left font-semibold">Vector ID</th>
              <th className="px-6 py-4 text-left font-semibold">
                Service Module
              </th>
              <th className="px-6 py-4 text-left font-semibold">Topology</th>
              <th className="px-6 py-4 text-left font-semibold">
                Hypothesis / Description
              </th>
              <th className="px-6 py-4 font-semibold text-center">Status</th>
              <th className="px-6 py-4 text-left font-semibold">Scripted</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-black/5 dark:divide-white/5">
            {filtered.map((test) => (
              <React.Fragment key={test.id}>
                <tr
                  onClick={() =>
                    setExpandedRow(expandedRow === test.id ? null : test.id)
                  }
                  className="cursor-pointer bg-white dark:bg-transparent hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group"
                >
                  <td className="px-6 py-4 font-bold text-gray-900 dark:text-gray-100 whitespace-nowrap">
                    {test.id}{" "}
                    {criticalIds.includes(test.id) && (
                      <span
                        className="text-amber-500 dark:text-amber-400 drop-shadow-sm ml-1"
                        title="Critical Vector"
                      >
                        ✦
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-600 dark:text-gray-300 font-medium">
                    {test.module}
                  </td>
                  <td className="px-6 py-4 capitalize text-gray-500 dark:text-gray-400">
                    {test.type.replace("_", " ")}
                  </td>
                  <td className="px-6 py-4 text-gray-700 dark:text-gray-300 max-w-md truncate">
                    {test.description}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-center">
                    {(() => {
                      const res = executionById.get(test.id);
                      if (!res) return <span className="text-gray-400">-</span>;
                      return (
                        <span
                          className={clsx(
                            "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase",
                            statusColors[res.status],
                          )}
                        >
                          {res.status}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="px-6 py-4 text-gray-500 dark:text-gray-400 font-semibold">
                    {test.automated ? (
                      <span className="text-accent underline decoration-accent/30 decoration-2 underline-offset-4">
                        Yes ▾
                      </span>
                    ) : (
                      "No"
                    )}
                  </td>
                </tr>
                {expandedRow === test.id && (
                  <tr>
                    <td colSpan={6} className="p-0 border-0">
                      <div className="bg-gray-50 dark:bg-black/60 border-y border-black/5 dark:border-white/10 px-6 py-5 space-y-4">
                        {/* Automation Snippet */}
                        {test.automation_snippet &&
                          test.automation_snippet.length > 0 && (
                            <div>
                              <div className="mb-3 flex items-center justify-between gap-3">
                                <div className="text-xs uppercase tracking-widest text-accent font-bold flex items-center gap-2">
                                  <svg
                                    className="w-4 h-4"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      strokeWidth={2}
                                      d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
                                    />
                                  </svg>
                                  Generated Automation Snippet
                                </div>
                                <button
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    handleCopySnippet(
                                      test.automation_snippet,
                                      test.id,
                                    );
                                  }}
                                  className="rounded-lg border border-black/10 dark:border-white/10 px-3 py-1 text-[11px] font-semibold text-gray-700 dark:text-gray-200 hover:bg-black/5 dark:hover:bg-white/10 transition"
                                >
                                  {copiedSnippetId === test.id
                                    ? "Copied"
                                    : "Copy"}
                                </button>
                              </div>
                              <pre className="text-sm text-gray-800 dark:text-emerald-400 overflow-x-auto whitespace-pre-wrap font-mono p-5 bg-white dark:bg-black/80 rounded-xl border border-gray-200 dark:border-white/5 shadow-inner">
                                {Array.isArray(test.automation_snippet)
                                  ? test.automation_snippet.join("\n")
                                  : test.automation_snippet}
                              </pre>
                            </div>
                          )}

                        {/* Execution Output */}
                        {(() => {
                          const res = executionById.get(test.id);
                          if (!res) {
                            return null;
                          }

                          const isPass = res.status === "pass";
                          const guidance = buildFailureGuidance(test, res);
                          const label = isPass
                            ? "Execution Output / Logs"
                            : "Execution Failure Evidence / Logs";
                          const boxClass = isPass
                            ? "text-sm text-emerald-800 dark:text-emerald-300 overflow-x-auto whitespace-pre-wrap font-mono p-5 bg-emerald-50 dark:bg-emerald-950/20 rounded-xl border border-emerald-200 dark:border-emerald-900/50 shadow-inner"
                            : "text-sm text-red-800 dark:text-red-400 overflow-x-auto whitespace-pre-wrap font-mono p-5 bg-red-50 dark:bg-red-950/20 rounded-xl border border-red-200 dark:border-red-900/50 shadow-inner";

                          const output =
                            res.error_message && res.error_message.trim()
                              ? res.error_message
                              : isPass
                                ? "Test passed successfully."
                                : "No execution output available.";

                          return (
                            <div>
                              <div
                                className={clsx(
                                  "text-xs uppercase tracking-widest mb-3 font-bold flex items-center gap-2",
                                  isPass ? "text-emerald-500" : "text-danger",
                                )}
                              >
                                <svg
                                  className="w-4 h-4"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  stroke="currentColor"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                                  />
                                </svg>
                                {label}
                              </div>
                              <div className={boxClass}>{output}</div>

                              {guidance && (
                                <div className="mt-4 rounded-xl border border-amber-200/80 dark:border-amber-500/30 bg-amber-50/70 dark:bg-amber-500/10 p-4">
                                  <div className="text-xs uppercase tracking-widest font-bold text-amber-700 dark:text-amber-300 mb-2">
                                    Why It Failed (Plain English)
                                  </div>
                                  <p className="text-sm text-amber-900 dark:text-amber-100 leading-relaxed">
                                    {guidance.reason}
                                  </p>

                                  <div className="mt-3 text-xs uppercase tracking-widest font-bold text-emerald-700 dark:text-emerald-300 mb-2">
                                    Suggested Fixes
                                  </div>
                                  <ul className="list-disc pl-5 space-y-1 text-sm text-gray-800 dark:text-gray-200">
                                    {guidance.suggestions.map((item, idx) => (
                                      <li
                                        key={`${guidance.context}-fix-${idx}`}
                                      >
                                        {item}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400 border-t border-black/5 dark:border-white/10">
            No test vectors match the current filters.
          </div>
        )}
      </div>
    </div>
  );
}
