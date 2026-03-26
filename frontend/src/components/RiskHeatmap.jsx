import React from "react";
import clsx from "clsx";

const riskColor = {
  critical: "bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/30",
  high: "bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-400 border border-orange-200 dark:border-orange-500/30",
  medium: "bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30",
  low: "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30",
};

export default function RiskHeatmap({ moduleRisks = [] }) {
  return (
    <div className="w-full h-full flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold tracking-widest uppercase text-gray-500 dark:text-gray-400">
          Module Risk Heatmap
        </h3>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-2 auto-rows-max">
        {moduleRisks.map((module) => (
          <div
            key={module.module}
            className="flex flex-col justify-between rounded-2xl border border-black/5 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-5 transition-transform hover:-translate-y-1 shadow-sm"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="text-sm font-bold text-gray-900 dark:text-white break-words">
                {module.module}
              </div>
              <span
                className={clsx(
                  "rounded-lg px-2 py-1 text-[10px] font-black uppercase tracking-wider whitespace-nowrap",
                  riskColor[module.regression_risk] || "bg-gray-100 text-gray-500",
                )}
              >
                {module.regression_risk} Risk
              </span>
            </div>
            <div className="mt-4 flex flex-col gap-1">
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">Failure Probability:</span>
                <span className="text-gray-900 dark:text-gray-200">{(module.defect_probability * 100).toFixed(0)}%</span>
              </div>
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-gray-500 dark:text-gray-400">Prior Defects:</span>
                <span className="text-gray-900 dark:text-gray-200">{module.historical_defect_count}</span>
              </div>
            </div>
            <div className="mt-3 text-[11px] font-medium text-amber-600 dark:text-amber-400 border-t border-black/5 dark:border-white/10 pt-3">
              <span className="block text-[10px] uppercase text-gray-400 mb-1">Top Failure Patterns:</span>
              {module.top_defect_types.join(", ")}
            </div>
            {module.vulnerability_heatmap && (
              <div className="mt-3 rounded-xl bg-red-50 dark:bg-red-500/10 p-3 text-[11px] text-red-700 dark:text-red-400 font-mono shadow-inner border border-red-200 dark:border-red-500/20">
                <div className="font-bold mb-1 uppercase tracking-wider">⚠️ Vulnerability Vector</div>
                {module.vulnerability_heatmap}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
