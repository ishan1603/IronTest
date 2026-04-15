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

const learningColors = {
  adaptive: "text-sky-700 dark:text-sky-200 bg-sky-100 dark:bg-sky-500/20",
  baseline:
    "text-emerald-700 dark:text-emerald-200 bg-emerald-100 dark:bg-emerald-500/20",
  fallback:
    "text-amber-700 dark:text-amber-200 bg-amber-100 dark:bg-amber-500/20",
};

function normalizeLearningSource(value) {
  const source = String(value || "baseline").toLowerCase();
  if (source === "adaptive" || source === "fallback") return source;
  return "baseline";
}

function deterministicIndex(seed, size) {
  if (!size) return 0;
  let hash = 0;
  const text = String(seed || "");
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  }
  return hash % size;
}

function extractSignal(message) {
  const text = String(message || "");
  if (!text.trim()) return "No concrete assertion signal captured.";

  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const preferred = lines.find(
    (line) =>
      line.startsWith("E   ") ||
      line.includes("AssertionError") ||
      line.includes("NameError") ||
      line.includes("TypeError") ||
      line.includes("Timeout") ||
      line.includes("FAILED"),
  );

  if (preferred) return preferred.replace(/^E\s+/, "");

  const tail = lines.slice(-4).join(" | ");
  return tail || "No concrete assertion signal captured.";
}

function extractDurationFromPytestLog(message) {
  const text = String(message || "");
  const match = text.match(/in\s+([0-9]+\.[0-9]+)s/);
  return match ? Number(match[1]) : null;
}

function buildFailureGuidance(test, result) {
  if (!result || (result.status !== "fail" && result.status !== "error")) {
    return null;
  }

  const message = String(result.error_message || "");
  const normalized = message.toLowerCase();
  const expected = String(test.expected_result || "expected contract");
  const signal = extractSignal(message);

  let reason = `Execution for ${test.id} in ${test.module} diverged from the expected contract.`;
  let suggestions = [
    `Compare actual output against expected contract: ${expected}.`,
    `Add a focused precondition assertion for ${test.module} before final validation to isolate drift earlier.`,
    `Use ${test.id} as a targeted regression gate once the fix lands.`,
  ];

  if (normalized.includes("timeout") || normalized.includes("timed out")) {
    reason = `The ${test.type.replace("_", " ")} path for ${test.module} exceeded timing assumptions, so assertions executed after the SLA window.`;
    suggestions = [
      `Profile slow calls used by ${test.id} and optimize the worst dependency first.`,
      `Keep timeout strict and fix latency root cause before relaxing thresholds for ${test.module}.`,
      `Add retry/backoff only for transient dependencies, not deterministic logic failures.`,
    ];
  } else if (
    normalized.includes("assert") ||
    normalized.includes("expected") ||
    normalized.includes("actual")
  ) {
    reason = `The assertion phase completed, but the observed output for ${test.module} did not satisfy expected behavior.`;
    suggestions = [
      `Reconcile payload fields against expected_result for ${test.id}: ${expected}.`,
      `Add intermediate assertions around ${test.module} transformation points to localize divergence.`,
      `Review boundary and edge handling paths linked to ${test.type.replace("_", " ")} behavior.`,
    ];
  } else if (
    normalized.includes("401") ||
    normalized.includes("403") ||
    normalized.includes("unauthorized") ||
    normalized.includes("forbidden")
  ) {
    reason = `Auth controls blocked ${test.id}, so the intended execution path in ${test.module} never reached business assertions.`;
    suggestions = [
      `Validate token/session scope used by ${test.id} and confirm it matches endpoint permissions.`,
      `Check role mapping for the principal used in ${test.module} tests.`,
      "Ensure auth headers and claim sets are present before request dispatch.",
    ];
  } else if (normalized.includes("404") || normalized.includes("not found")) {
    reason = `A required route/entity was missing during ${test.id}, interrupting ${test.module} flow.`;
    suggestions = [
      "Verify endpoint and route mapping for this environment before execution.",
      `Create prerequisite records used by ${test.id} during setup stage.`,
      "Add explicit setup validation so missing entities fail fast with clear diagnostics.",
    ];
  } else if (
    normalized.includes("500") ||
    normalized.includes("internal server") ||
    normalized.includes("exception")
  ) {
    reason = `Internal exception interrupted ${test.module} before ${test.id} reached its final assertion.`;
    suggestions = [
      `Inspect stack trace paths that touch ${test.module} and correlate with ${test.id}.`,
      "Harden null/invalid input guards in this execution path.",
      "Add a focused unit test for the specific failing branch to prevent recurrence.",
    ];
  } else if (
    normalized.includes("connect") ||
    normalized.includes("econn") ||
    normalized.includes("network") ||
    normalized.includes("dns") ||
    normalized.includes("socket")
  ) {
    reason = `Connectivity instability prevented ${test.id} from reaching required dependencies at runtime.`;
    suggestions = [
      `Confirm host/port targets used by ${test.module} are reachable in this environment.`,
      "Validate network routing and firewall rules for dependent services.",
      "Gate execution with dependency health checks before integration tests begin.",
    ];
  } else if (
    normalized.includes("json") ||
    normalized.includes("schema") ||
    normalized.includes("validation") ||
    normalized.includes("type")
  ) {
    reason = `Contract/schema mismatch was detected for ${test.module}, causing validation failure in ${test.id}.`;
    suggestions = [
      "Compare runtime payload against contract and required keys before assertions.",
      "Normalize field types at boundary adapters before schema validation.",
      "Add pre-check schema validation to fail early with actionable diagnostics.",
    ];
  }

  return {
    reason: `${reason} Signal: ${signal}`,
    suggestions,
    context: `${test.id} (${test.module})`,
  };
}

function buildTestNarrative(test, result) {
  if (!result) {
    return {
      doing: `This vector validates ${test.type.replace("_", " ")} behavior for ${test.module}: ${test.description}`,
      why: "Execution not available yet for this test case.",
      suggestions: [
        "Run the pipeline to capture real execution evidence and risk signals.",
      ],
    };
  }

  const status = String(result.status || "").toLowerCase();
  const expected = String(
    test.expected_result || "Expected outcome not provided.",
  );
  const stepCount = Array.isArray(test.steps) ? test.steps.length : 0;
  const runtime = extractDurationFromPytestLog(result.error_message);
  const signal = extractSignal(result.error_message);

  const doing = `This test validates ${test.type.replace("_", " ")} behavior in ${test.module}. Hypothesis: ${test.description}. Expected: ${expected}`;

  if (status === "pass") {
    const passVariants = [
      `Execution matched the expected contract for ${test.module}, and assertions closed cleanly without runtime defects.`,
      `The ${test.type.replace("_", " ")} checks remained stable in ${test.module}, and observed output aligned with expected behavior.`,
      `${test.id} passed because observed state transitions and final output stayed consistent with the acceptance expectation.`,
    ];
    const variant =
      passVariants[
        deterministicIndex(
          `${test.id}|pass|${test.module}`,
          passVariants.length,
        )
      ];
    const runtimeNote =
      runtime !== null ? ` Runtime: ${runtime.toFixed(2)}s.` : "";
    return {
      doing,
      why: `${variant} Scope: ${stepCount} verification steps.${runtimeNote}`,
      suggestions: [],
    };
  }

  const guidance = buildFailureGuidance(test, result);
  return {
    doing,
    why:
      guidance?.reason ||
      `Execution diverged from expected behavior for this scenario. Signal: ${signal}`,
    suggestions: guidance?.suggestions || [
      `Compare expected_result with observed evidence for ${test.id}.`,
      `Re-run ${test.module} checks with focused debug tracing around failing assertions.`,
    ],
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
              <th className="px-6 py-4 text-left font-semibold">Learning</th>
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
                  <td className="px-6 py-4 text-gray-700 dark:text-gray-300 max-w-3xl whitespace-normal leading-relaxed">
                    {test.description}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {(() => {
                      const source = normalizeLearningSource(
                        test.learning_source,
                      );
                      const label =
                        source === "adaptive"
                          ? "Adaptive"
                          : source === "fallback"
                            ? "Fallback"
                            : "Baseline";
                      return (
                        <span
                          className={clsx(
                            "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase",
                            learningColors[source],
                          )}
                        >
                          {label}
                        </span>
                      );
                    })()}
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
                    <td colSpan={7} className="p-0 border-0">
                      <div className="bg-gray-50 dark:bg-black/60 border-y border-black/5 dark:border-white/10 px-6 py-5 space-y-4">
                        <div className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-black/30 p-4">
                          <div className="text-xs uppercase tracking-widest font-bold text-gray-500 dark:text-gray-400 mb-2">
                            Learning Evidence
                          </div>
                          <div className="grid gap-3 md:grid-cols-3 text-sm">
                            <div>
                              <div className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                                Source
                              </div>
                              <div className="font-semibold text-gray-800 dark:text-gray-200 mt-1">
                                {normalizeLearningSource(test.learning_source)}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                                Derived Signature
                              </div>
                              <div className="font-semibold text-gray-800 dark:text-gray-200 mt-1 break-words">
                                {test.derived_from_failure_signature || "N/A"}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                                Novelty Reason
                              </div>
                              <div className="font-semibold text-gray-800 dark:text-gray-200 mt-1 break-words">
                                {test.novelty_reason ||
                                  "Known behavior path re-validated."}
                              </div>
                            </div>
                          </div>
                        </div>

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

                              {(() => {
                                const narrative = buildTestNarrative(test, res);
                                return (
                                  <div className="mt-4 rounded-xl border border-cyan-200/80 dark:border-cyan-500/30 bg-cyan-50/70 dark:bg-cyan-500/10 p-4">
                                    <div className="text-xs uppercase tracking-widest font-bold text-cyan-700 dark:text-cyan-300 mb-2">
                                      What this test case is doing
                                    </div>
                                    <p className="text-sm text-cyan-900 dark:text-cyan-100 leading-relaxed">
                                      {narrative.doing}
                                    </p>

                                    <div className="mt-3 text-xs uppercase tracking-widest font-bold text-indigo-700 dark:text-indigo-300 mb-2">
                                      Why this test case{" "}
                                      {isPass ? "passes" : "fails"}
                                    </div>
                                    <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
                                      {narrative.why}
                                    </p>

                                    {!isPass && (
                                      <>
                                        <div className="mt-3 text-xs uppercase tracking-widest font-bold text-emerald-700 dark:text-emerald-300 mb-2">
                                          Smart suggestions to make it pass
                                        </div>
                                        <ul className="list-disc pl-5 space-y-1 text-sm text-gray-800 dark:text-gray-200">
                                          {narrative.suggestions.map(
                                            (item, idx) => (
                                              <li
                                                key={`${test.id}-narrative-${idx}`}
                                              >
                                                {item}
                                              </li>
                                            ),
                                          )}
                                        </ul>
                                      </>
                                    )}
                                  </div>
                                );
                              })()}
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
