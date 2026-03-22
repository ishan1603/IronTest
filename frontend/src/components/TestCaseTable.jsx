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
  low: "bg-success/20 text-success",
  medium: "bg-amber-200/10 text-amber-200",
  high: "bg-danger/10 text-danger",
};

export default function TestCaseTable({ tests = [], criticalIds = [] }) {
  const [typeFilter, setTypeFilter] = useState("all");
  const [riskFilter, setRiskFilter] = useState("all");

  const filtered = useMemo(() => {
    return tests.filter((t) => {
      const typeOk = typeFilter === "all" || t.type === typeFilter;
      const riskOk = riskFilter === "all" || t.risk_level === riskFilter;
      return typeOk && riskOk;
    });
  }, [tests, typeFilter, riskFilter]);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/30 backdrop-blur-xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-gray-100">
            Generated Test Cases
          </h3>
          <p className="text-sm text-gray-400">
            {tests.length} Test Cases Generated
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          {Object.entries(typeLabels).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setTypeFilter(value)}
              className={clsx(
                "rounded-full px-3 py-1",
                typeFilter === value
                  ? "bg-accent text-white"
                  : "bg-white/5 text-gray-200",
              )}
            >
              {label}
            </button>
          ))}
          {[
            ["all", "All Risk"],
            ["low", "Low"],
            ["medium", "Medium"],
            ["high", "High"],
          ].map(([value, label]) => (
            <button
              key={value}
              onClick={() => setRiskFilter(value)}
              className={clsx(
                "rounded-full px-3 py-1",
                riskFilter === value
                  ? "bg-accent text-white"
                  : "bg-white/5 text-gray-200",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="min-w-full text-sm">
          <thead className="bg-white/5 text-gray-200">
            <tr>
              <th className="px-4 py-3 text-left">ID</th>
              <th className="px-4 py-3 text-left">Module</th>
              <th className="px-4 py-3 text-left">Type</th>
              <th className="px-4 py-3 text-left">Description</th>
              <th className="px-4 py-3 text-left">Risk</th>
              <th className="px-4 py-3 text-left">Automated</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((test) => (
              <tr
                key={test.id}
                className="border-t border-white/5 odd:bg-white/5"
              >
                <td className="px-4 py-3 font-semibold text-gray-100">
                  {test.id}{" "}
                  {criticalIds.includes(test.id) && (
                    <span className="text-amber-300">⭐</span>
                  )}
                </td>
                <td className="px-4 py-3 text-gray-200">{test.module}</td>
                <td className="px-4 py-3 capitalize text-gray-300">
                  {test.type.replace("_", " ")}
                </td>
                <td className="px-4 py-3 text-gray-300">{test.description}</td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "rounded-full px-2 py-1 text-xs font-semibold",
                      riskColors[test.risk_level],
                    )}
                  >
                    {test.risk_level}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-200">
                  {test.automated ? "Yes" : "No"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
