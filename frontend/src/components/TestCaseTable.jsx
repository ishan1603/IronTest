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

export default function TestCaseTable({
  tests = [],
  execution = [],
  criticalIds = [],
}) {
  const [typeFilter, setTypeFilter] = useState("all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [expandedRow, setExpandedRow] = useState(null);

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
                      const res = execution.find((r) => r.test_id === test.id);
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
                              <div className="text-xs uppercase tracking-widest text-accent mb-3 font-bold flex items-center gap-2">
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
                              <pre className="text-sm text-gray-800 dark:text-emerald-400 overflow-x-auto whitespace-pre-wrap font-mono p-5 bg-white dark:bg-black/80 rounded-xl border border-gray-200 dark:border-white/5 shadow-inner">
                                {Array.isArray(test.automation_snippet)
                                  ? test.automation_snippet.join("\n")
                                  : test.automation_snippet}
                              </pre>
                            </div>
                          )}

                        {/* Execution Failure Evidence */}
                        {(() => {
                          const res = execution.find(
                            (r) => r.test_id === test.id,
                          );
                          if (
                            res &&
                            res.status !== "pass" &&
                            res.error_message
                          ) {
                            return (
                              <div>
                                <div className="text-xs uppercase tracking-widest text-danger mb-3 font-bold flex items-center gap-2">
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
                                  Execution Failure Evidence / Logs
                                </div>
                                <div className="text-sm text-red-800 dark:text-red-400 overflow-x-auto whitespace-pre-wrap font-mono p-5 bg-red-50 dark:bg-red-950/20 rounded-xl border border-red-200 dark:border-red-900/50 shadow-inner">
                                  {res.error_message}
                                </div>
                              </div>
                            );
                          }
                          return null;
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
